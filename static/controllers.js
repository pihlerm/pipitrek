import * as THREE from 'three';

export class Controllers {
    constructor(renderer, userRig, scene) {
        // left and right controllers
        this.Left = null;
        this.LeftGamepad = null;
        this.Right = null;
        this.RightGamepad = null;
        this.currentPositionL = new THREE.Vector3();
        this.lastPositionL = new THREE.Vector3();
        this.lastLocalPositionL = new THREE.Vector3();
        this.currentPositionR = new THREE.Vector3();
        this.lastPositionR = new THREE.Vector3();
        this.lastLocalPositionR = new THREE.Vector3();
        this.velocityL = new THREE.Vector3();   
        this.velocityR = new THREE.Vector3();   
        this.lastTime = 0;
        this.scene = scene;
        // WebXR controller events:
        // selectstart Fired when the primary action button (typically the trigger) is pressed.
        // selectend Fired when the primary action button (trigger) is released.
        // select Fired when a complete select action occurs (press and release of the trigger).
        // squeezestart Fired when the secondary action button (typically the grip or squeeze button) is pressed.
        // squeezeend
        // squeeze

        // Additional events
        this.prepareCallbacks();

        // Prepare controller slots
        const controller0 = renderer.xr.getController(0);
        const controller1 = renderer.xr.getController(1);

        // Handle when controllers connect
        const onControllerConnected = (event) => {
            const handedness = event.data.handedness;
            const controller = event.target;

            function addLaser(controller, color) {
                const laserGeometry = new THREE.CylinderGeometry(0.002, 0.002, 1, 8);
                laserGeometry.translate(0, 0.5, 0); // Make it start at controller (Y origin to Y+1)
                const laserMaterial = new THREE.MeshBasicMaterial({ color: color });
                const laser = new THREE.Mesh(laserGeometry, laserMaterial);                
                laser.rotation.set(-Math.PI / 2, 0, 0); // Point along Z
                laser.scale.set(1, 100, 1); 
                controller.userData.laser = laser;
                controller.userData.color = color;
                controller.add(laser);
            }

            if (handedness === 'right') {
                console.log('Right controller connected!');
                this.Right = controller;
                this.RightGamepad = event.data.gamepad || null; // <-- store gamepad reference!
                addLaser(controller, 0xff0000);
                userRig.add(controller);
                this.lastPositionR.copy(controller.position);
                if(this.onRConnectedCallback) this.onRConnectedCallback(controller);
            }
            if (handedness === 'left') {
                console.log('Left controller connected!');
                this.Left = controller;
                this.LeftGamepad = event.data.gamepad || null; // <-- store gamepad reference!
                addLaser(controller, 0x00aa00);
                userRig.add(controller);
                this.lastPositionL.copy(controller.position);
                if(this.onLConnectedCallback) this.onLConnectedCallback(controller);
            }
        }

        // Listen for connected event on both controller slots
        controller0.addEventListener('connected', onControllerConnected);
        controller1.addEventListener('connected', onControllerConnected); 
    }

    prepareCallbacks() {
        this.Rcallbacks = [];         
        this.Lcallbacks = [];
        this.onRConnectedCallback = null;
        this.onLConnectedCallback = null;
        for(var i=0; i<7; i++) {
            this.Rcallbacks.push({start: null, end:null, press:null, pressed: false, interval:0, lastTime:0});
            this.Lcallbacks.push({start: null, end:null, press:null, pressed: false, interval:0, lastTime:0});
        }
    }

    onRConnected(callback) {
        this.onRConnectedCallback = callback;
    }
    onLConnected(callback) {
        this.onLConnectedCallback = callback;
    }

    attachEvent(side, button, action, callback, interval=null) {
        
        if(button > 6 || button<0) throw new Error("Invalid argument: button must be between 0 and 6.");
        
        const btn = (side == "left" ? this.Lcallbacks[button] : this.Rcallbacks[button]);
        
        if(interval != null) btn.interval = interval;

        if(action == 'start') {
            btn.start = callback;
        } else if(action == 'end') {
            btn.end = callback;
        } else if(action == 'press') {
            btn.press = callback;            
        } else {
            throw new Error("Invalid argument: action must be start/end/press");
        }
    }

    attachLaser(controller) {
        const laser = controller.userData.laser;
        if (laser.parent !== controller) {
            this.scene.remove(laser);
            controller.add(laser);
            // Reset orientation
            laser.position.set(0, 0, 0);
            laser.rotation.set(-Math.PI / 2, 0, 0); // Point along -Z
            laser.scale.set(1, 100, 1); 
            laser.material.color.set(controller.userData.color); // Red
        }
    }
    pointLaser(side, objectPos, color=null) {
        const controller = (side == 'left' ? this.Left : this.Right);
        const laser = controller.userData.laser;
        if (laser.parent !== this.scene) {
            controller.remove(laser);
            this.scene.add(laser);
            if(color == null) color = 0xffff00;
            laser.material.color.set(color); // Yellow
        }

        const controllerPos = (side == 'left' ? this.currentPositionL : this.currentPositionR);
        // Get world positions
        const direction = new THREE.Vector3().subVectors(objectPos, controllerPos);
        const distance = direction.length();
        direction.normalize();

        // Set position of laser
        laser.position.copy(controllerPos);

        // Set orientation - laser originally points in +Y
        const up = new THREE.Vector3(0, 1, 0);
        laser.quaternion.setFromUnitVectors(up, direction);

        // Set scale (stretch along Y)
        laser.scale.set(1, distance, 1);
    }

    hapticFeedback(side) {
        const gp = (side == "left" ? this.LeftGamepad : this.RightGamepad);
        if (gp?.hapticActuators?.length) {
            gp.hapticActuators[0].pulse(0.5, 100); // Intensity 0.5, 100ms
        }
    }

    handleButtons(time, buttons, state) {
        for(var i=0; i<buttons.length && i<state.length; i++) {
            const btn = buttons[i];
            const st = state[i];
            if(btn.pressed  && !st.pressed && time > (st.lastTime + st.interval)) {
                st.pressed = btn.pressed;
                st.lastTime = time;
                if(st.start) st.start();
            } else if(!btn.pressed  && st.pressed) {
                st.pressed = btn.pressed;
                if(st.end) st.end();
                if(st.press) st.press();
            }
            
        }
    }

    updateVectors(deltaTime) {
        if (this.Right) {
            this.lastPositionR.copy(this.currentPositionR);
            this.Right.updateMatrixWorld(true);
            this.Right.getWorldPosition(this.currentPositionR);
            if (deltaTime > 0.01) {
                this.velocityR.subVectors(this.Right.position, this.lastLocalPositionR).divideScalar(deltaTime);
                this.lastLocalPositionR.copy(this.Right.position);
            } else {
                this.velocityR.set(0, 0, 0);
            }
        }
        if (this.Left) {
            this.lastPositionL.copy(this.currentPositionL);
            this.Left.updateMatrixWorld(true);
            this.Left.getWorldPosition(this.currentPositionL);
            if (deltaTime > 0.01) {
                this.velocityL.subVectors(this.Left.position, this.lastLocalPositionL).divideScalar(deltaTime);
                this.lastLocalPositionL.copy(this.Left.position);
            } else {
                this.velocityL.set(0, 0, 0);
            }
        }
    }

    handleControllers(time) {
        this.updateVectors(time - this.lastTime);
        this.lastTime = time;
        if (this.RightGamepad) {
            this.handleButtons(time, this.RightGamepad.buttons, this.Rcallbacks);
        }
        if (this.LeftGamepad) {
            this.handleButtons(time, this.LeftGamepad.buttons, this.Lcallbacks);
        }
    }

    LthumbAxes() {
        if(this.LeftGamepad) {
            return [this.LeftGamepad.axes[2] || 0, this.LeftGamepad.axes[3] || 0];
        } else {
            return [0,0];
        }        
    }
    RthumbAxes() {
        if(this.RightGamepad) {
            return [this.RightGamepad.axes[2] || 0, this.RightGamepad.axes[3] || 0];
        } else {
            return [0,0];
        }        
    }
}