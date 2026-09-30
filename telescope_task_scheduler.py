"""A small scheduler for running telescope tasks in the background."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Optional
from threading import RLock
import autoguider
from telescope_task import *


# Maps task list JSON "type" values to constructors for the classes in telescope_task.py.
TASK_BUILDERS = {
    'Slew': lambda t, tel, cam, ag: TelescopeSlewingTask(tel, t.get('target_ra'), t.get('target_dec'), ag),
    'Imaging': lambda t, tel, cam, ag: TelescopeImagingTask(tel, float(t.get('exposure_time')), int(t.get('exposure_count')), camera=cam, autoguider=ag),
    'MeridianFlip': lambda t, tel, cam, ag: TelescopeMeridianFlipTask(tel),
    'InitializePosition': lambda t, tel, cam, ag: TelescopeInitializePositionTask(tel, cam, ag),
    'StartAutoguider': lambda t, tel, cam, ag: TelescopeStartAutoguiderTask(tel, ag, calibrate_axis=(t.get('calibrate_axis'))),
    'StopAutoguider': lambda t, tel, cam, ag: TelescopeStopAutoguiderTask(tel, ag),
    'Park': lambda t, tel, cam, ag: TelescopeParkTask(tel),
}


class TelescopeTaskScheduler:
    """Thread-safe, one-shot task scheduler suitable for telescope operations."""

    def __init__(self, camera, telescope, autoguider) -> None:
        self._task_list: list[dict[str, Any]] = []
        self.task_list_thread: Optional[threading.Thread] = None
        self._running = False
        self.needs_stop = False
        self._task_instance = None          # current running task instance
        self._task_dict = None              # current running task dictionary
        self.camera = camera
        self.telescope = telescope
        self.autoguider = autoguider
        self.last_task_id = 0
        self.lock = RLock()  # guards all access to _task_list and the fields below
        self.load_task_list("task_list.json")

    def start(self):
        if self._running:
           return False  # A task list is already running, so we exit early.
        with self.lock:
            self._running = True
            self.needs_stop = False
            self._task_instance = None
            self._task_dict = None
            self.task_list_thread = threading.Thread(target=self.run_task_list, args=(), daemon=True)
            self.task_list_thread.start()
        return True

    def is_running(self) -> bool:
        with self.lock:
            return self._running

    def stop(self):
        with self.lock:
            self.needs_stop = True
            if self._task_instance is not None:
                self._task_instance.stop()
        if self.task_list_thread is not None:
            self.task_list_thread.join(timeout=30)        

    def save_task_list(self, file_path: str) -> None:
        with self.lock:
            import json
            with open(file_path, 'w') as f:
                json.dump(self._task_list, f, indent=4)
            print(f"Task list saved to {file_path}")

    def load_task_list(self, file_path: str) -> None:
        with self.lock:
            import json
            try:
                with open(file_path, 'r') as f:
                    self._task_list = json.load(f)
                print(f"Task list loaded from {file_path}")
                for i, task_dict in enumerate(self._task_list):
                    if 'id' not in task_dict:
                        del self._task_list[i]
                        continue
                    if self.last_task_id < task_dict['id']:
                        self.last_task_id = task_dict['id']
                self.estimateTime()

            except FileNotFoundError:
                print(f"Task list file {file_path} not found. Starting with an empty task list.")
                self._task_list = []

    def get_task_list_status(self) -> dict[str, Any]:
        with self.lock:
            current_task_progress = None
            if self._task_instance is not None:
                current_task_progress = self._task_instance.percent_complete()
            return {
                "running": self._running,
                "total": len(self._task_list),
                "current_task_id": self._task_dict.get('id') if self._task_dict is not None else -1,
                "current_task_progress": current_task_progress,
                "task_status": [task.get('status') for task in self._task_list]
            }

    def get_task_list(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(task) for task in self._task_list]

    def get_task(self, task_id) -> dict[str, Any] | None:
        with self.lock:
            for task_dict in self._task_list:
                if task_dict.get('id') == task_id:
                    return dict(task_dict)
            return None

    def add_to_task_list(self, tasks):
        # Safe to call while run_task_list is iterating: new tasks are only ever appended.
        with self.lock:
            for task_dict in tasks:
                task_dict['status'] = "pending"
                self._assign_task_id(task_dict)
                self._task_list.append(task_dict)
            self.estimateTime()

    def remove_from_task_list(self, task_id) -> bool:
        #Removes a queued task by id. If the task is currently running, attempt to stop it.
        with self.lock:
            for i, task_dict in enumerate(self._task_list):
                if task_dict.get('id') != task_id:
                    continue
                if self._task_dict is not None and self._task_dict.get('id') == task_id:
                    if self._task_instance is not None:
                        self._task_instance.stop()
                else:
                    del self._task_list[i]
                self.estimateTime()
                return True
            return False

    def _assign_task_id(self, task):
        # Caller must hold self.lock.
        self.last_task_id += 1
        task['id'] = self.last_task_id

    def estimateTime(self) -> float:
        # Caller must hold self.lock.
        last_time = time.time()
        for i, task_dict in enumerate(self._task_list):
            if task_dict.get('status') == "finished" or task_dict.get('status') == "error":
                continue

            task_type = task_dict.get('type')
            builder = TASK_BUILDERS.get(task_type)
            if builder is None:
                print(f"Unknown task type: {task_type}")
                return False

            if task_dict.get('status') == "running":
                last_time = task_dict.get('start_time')
                if last_time is None:
                    last_time = time.time()
            else:
                task_dict['start_time'] = last_time

            try:
                task_instance = builder(task_dict, self.telescope, self.camera, self.autoguider)
                if task_dict.get('status') == "running":
                    last_time += task_instance.time_estimate()
                else:
                    last_time += task_instance.time
                task_dict['end_time'] = last_time
            except Exception as e:
                print(f"Failed to build task instance for task id {task_dict.get('id')}: {e}")
                return False
                    
        return True
            

    def run_task_list(self):

        print("Starting task list execution...")
        with self.lock:
            self._running = True
            self._task_instance = None
            self._task_dict = None
        try:
            i = 0
            while True:
                with self.lock:
                    # find first task that is not finished or in error
                    self._task_dict = None
                    for i, task_dict in enumerate(self._task_list):
                        status = task_dict.get('status')
                        if status != "finished" and status != "error":
                            self._task_dict = task_dict
                            break
                        
                    if self._task_dict is None:
                        if self.needs_stop:
                            break
                        time.sleep(0.5)  # small delay to prevent tight loop
                        continue
                    
                    task_dict = self._task_dict
                    task_type = task_dict.get('type')
                    status = task_dict.get('status')

                builder = TASK_BUILDERS.get(task_type)
                if builder is None:
                    with self.lock:
                        print(f"Unknown task type: {task_type}")
                        task_dict['status'] = {'status': 'error', 'message': f'Unknown task type: {task_type}'}
                    continue
                try:
                    print(f"Starting task execution for task id {task_dict.get('id')}...")
                    self._task_instance = builder(task_dict, self.telescope, self.camera, self.autoguider)
                    with self.lock:
                        task_dict['status'] = "running"
                        task_dict['result'] = {'id': task_dict.get('id'),'status': 'running'}
                        task_dict['start_time'] = time.time()
                    result = self._task_instance.execute()
                    result['id'] = task_dict.get('id')
                except Exception as e:
                    with self.lock:
                        task_dict['end_time'] = time.time()
                    result = {'id': task_dict.get('id'), 'status': 'error', 'message': str(e)}
                    task_dict['status'] = "error"

                print(f"Finished task execution for task id {task_dict.get('id')}, result: {result['status']}...")

                with self.lock:
                    task_dict['status'] = "finished"
                    task_dict['result'] = result
                    if self._task_instance and self._task_instance.end_time!=0:
                        task_dict['end_time'] = self._task_instance.end_time
                    if self._task_instance and self._task_instance.start_time!=0:
                        task_dict['start_time'] = self._task_instance.start_time
                    should_stop = isinstance(result, dict) and result.get('status') == 'error'
                    if should_stop:
                        task_dict['status'] = "error"
                    self.estimateTime()
                    self._task_instance = None
                    self._task_dict = None

                if self.needs_stop or should_stop:
                    break
                i += 1
                time.sleep(0.1)  # small delay to prevent tight loop
        finally:
            print(f"Stopping task execution...")
            with self.lock:
                self._running = False
                self._task_list_current_index = -1
                self._task_instance = None
                self._task_dict = None


