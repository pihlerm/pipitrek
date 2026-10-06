    function scopeSubmit(name, body) {
        fetch(name, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: body
        })
        .then(response => {
            if (!response.ok) {
                // Throw an error to trigger the .catch block
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json(); // Parse the JSON response
        })
        .then(data => {
            scopeAppendToResult('Success: ' + JSON.stringify(data));
        })
        .catch(error => scopeAppendToResult('Error:', error.message));
    }


    function scopeSubmitSetting(name, value) {
        scopeSubmit(`/set_${name}`,`${name}=${value}`);
    }

    function scopeSubmitJSON(name, obj) {

        fetch(name, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(obj)
        })
        .then(response => {
            if (!response.ok) {
                // Throw an error to trigger the .catch block
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json(); // Parse the JSON response
        })
        .then(data => {
            scopeAppendToResult('Success: ' + JSON.stringify(data));
        })
        .catch(error => scopeAppendToResult('Error:', error.message));
    }


    function submitProperty(name, value) {
        fetch('/set_direct_camera_property', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ "name" : name, "value" : value }),
        })
        .then(response => console.log(`Property ${name} set to ${value}`))
        .catch(error => console.error(`Error setting property ${name}:`, error));
    }



    function setPier(pier) {
        scopeSubmitSetting("pier", pier);
    }

    function setTracking(isTracking) {
        scopeSubmitSetting("tracking", isTracking);
    }

    function setQuiet(isQuiet) {
        scopeSubmitSetting("quiet", isQuiet);
    }

    function setLocked(isLocked) {
        scopeSubmitSetting("locked", isLocked);
    }

    function setPECPosition() {
        scopeSubmitSetting("pec_position", PEC_wheel.getPECPosition());
    }

    function sendDirection(direction) {
        scopeSubmit('/control_move',
            `direction=${direction}`
        );
    }

    function sendSpeed(speed) {
        scopeSubmit('/control_speed',
            `speed=${speed}`
        );
    }

    function sendStop() {
        scopeSubmit('/control_stop',
            `direction=`
        );
    }

    function setPECEnabled(enable) {
        scopeSubmit('/set_pec_enabled',
            `enable=${enable}`
        );
    }


    function submitCamera() {
        const shots = document.getElementById('shots-input').value.trim();
        const exposure = document.getElementById('exposure-input').value.trim();
        scopeSubmitJSON('/set_camera',
            { shots: shots, exposure: exposure }
        );
    }

    function startCamera() {
        btnCamStart = document.getElementById('camera-shooting');
        scopeSubmitJSON('/command_camera',
            {action: btnCamStart.innerText}
        );
    }

    function submitBacklash() {
        const ra = document.getElementById('bc_ra-input').value.trim();
        const dec = document.getElementById('bc_dec-input').value.trim();
        scopeSubmitJSON('/set_backlash',
            { ra: ra, dec: dec }
        );
    }

    function submitGoto(direct = false) {
        if (document.getElementById('guiding').checked) {
            scopeAppendToResult('Disabled while guiding');
            return;
        }

        const ra = document.getElementById('ra-input').value.trim();
        const dec = document.getElementById('dec-input').value.trim();

        if (!validateRA(ra) || !validateDEC(dec)) {
            scopeAppendToResult('Error: Invalid RA or DEC format.');
            return;
        }
        if (direct) {
            scopeSubmitJSON('/command_goto_direct',
                { ra: ra, dec: dec }
            );
        } else {
            scopeSubmitJSON('/command_goto',
                { ra: ra, dec: dec }
            );
        }
    }

    function submitSetTo() {
        const ra = document.getElementById('ra-input').value.trim();
        const dec = document.getElementById('dec-input').value.trim();

        if (!validateRA(ra) || !validateDEC(dec)) {
            scopeAppendToResult('Error: Invalid RA or DEC format.');
            return;
        }
        scopeSubmitJSON('/command_set_to',
            { ra: ra, dec: dec }
        );
    }


    function uploadFirmware() {
        const form = document.getElementById('uploadForm');
        const formData = new FormData(form);
        scopeAppendToResult('Starting firmware upload. Please do not disconnect telescope.');
        fetch('/command_upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            scopeAppendToResult('Upload Success: ' + JSON.stringify(data, null, 2));
            document.getElementById('firmware').files.length = 0; // Clear the file input
            document.getElementById('upload-firmware-button').classList.remove('red');
        })
        .catch((error) => {
            scopeAppendToResult('Error: ' + error);
        });
    }

    function resetArduino() {
        if (confirm("Are you sure you want to reset the Arduino?")) {
            scopeSubmit('/command_reset', '');
        } else {
            scopeAppendToResult('Arduino reset canceled.');
        }
    }

    function getInfo() {
        fetch('/command_info', {
            method: 'GET'
        })
        .then(response => response.json())
        .then(data => {
            setInfo(data.info)
        })
        .catch((error) => {
            scopeAppendToResult('Error: ' + error);
        });
    }


    function submitChannels() {
        const r_channel = document.getElementById('r_channel').value;
        const g_channel = document.getElementById('g_channel').value;
        const b_channel = document.getElementById('b_channel').value;

        document.getElementById('r_channel_value').textContent = r_channel;
        document.getElementById('g_channel_value').textContent = g_channel;
        document.getElementById('b_channel_value').textContent = b_channel;


        fetch('/set_channels', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ r_channel, g_channel, b_channel }),
        })
    }

    function submitJSON(name, obj) {
        return fetch(name, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(obj)
        });
    }


    function submitSetting(name, value, axis) {
        fetch(`/set_${name}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: `${name}=${value}&axis=${axis}`
        });        
    }

    function submitSaveFrames(value) {
        submitSetting("save_frames", value);
    }

    function submitThreshold() {
        const threshold = document.getElementById('threshold').value;
        document.getElementById('threshold_value').textContent = threshold;
        submitSetting("threshold", threshold);
    }
    function submitAutoThreshold() {
        const auto_threshold = document.getElementById('auto_threshold').checked;
        submitSetting("auto_threshold", auto_threshold);
    }
    function submitMaxDrift(axis) {
        const max_drift = document.getElementById(`max_drift_${axis}`).value;
        document.getElementById(`max_drift_${axis}_value`).textContent = max_drift;
        submitSetting("max_drift", max_drift, axis);
    }

    function submitMinStarSize() {
        const min_star_size = document.getElementById('min_star_size').value;
        document.getElementById('min_star_size_value').textContent = min_star_size;
        submitSetting("min_star_size", min_star_size);
    }

    function submitMaxStarSize() {
        const max_star_size = document.getElementById('max_star_size').value;
        document.getElementById('max_star_size_value').textContent = max_star_size;
        submitSetting("max_star_size", max_star_size);
    }

    function submitRotationAngle() {
        const rotation_angle = document.getElementById('rotation_angle').value;
        document.getElementById('rotation_angle_value').textContent = rotation_angle;
        submitSetting("rotation_angle", rotation_angle);
    }

    function submitPixelScale() {
        const pixel_scale = document.getElementById('pixel_scale').value;
        document.getElementById('pixel_scale_value').textContent = pixel_scale;
        submitSetting("pixel_scale", pixel_scale);
    }

    function submitGuideInterval() {
        const guide_interval = document.getElementById('guide_interval').value;
        document.getElementById('guide_interval_value').textContent = guide_interval;
        document.getElementById('guide_interval_auto').textContent = Number(guide_interval) === 0 ? 'auto' : '';
        submitSetting("guide_interval", guide_interval);
    }
    
    function submitGuidePulse() {
        const guide_pulse = document.getElementById('guide_pulse').value;
        document.getElementById('guide_pulse_value').textContent = guide_pulse;
        submitSetting("guide_pulse", guide_pulse);
    }

    function submitGuideMethod(value, axis) {
        submitSetting("guide_method", value, axis);
    }
    
    function submitIntegrate_frames() {
        const integrate_frames = document.getElementById('integrate_frames').value;
        document.getElementById('integrate_frames_value').textContent = integrate_frames;
        submitCameraProperties(JSON.stringify({ "integrate_frames":integrate_frames }));
    }

    function submitCameraFPS(value) {
        submitCameraProperties(JSON.stringify({ "camera_fps":value }));
    }
    function submitVideoMode(value) {
        submitCameraProperties(JSON.stringify({ "video_mode":value }));
    }
    function submitResolution(value) {
        const [width, height] = value.split('x').map(Number); // Split and convert to numbers
        submitCameraProperties(JSON.stringify({ width, height }));
    }

    function submitCameraColor(value) {        
        submitCameraProperties(JSON.stringify({ "camera_color" : value }));
    }

    function submitExposure(value) {        
        document.getElementById('camera_exposure_value').textContent = value;
        submitCameraProperties(JSON.stringify({ "camera_exposure" : value }));
    }

    function selectCamera(value) {        
        submitCameraProperties(JSON.stringify({ "camera_index" : value })).then(() => {
            loadCameraProperties();
        });        
    }


    function captureHotPixelMask() {
        submitSetting("hot_pixel_mask", true);
    }

    function clearHotPixelMask() {
        submitSetting("hot_pixel_mask", false);
    }

    function populateCameraList() {
        fetch('/get_camera_list')
            .then(response => response.json())
            .then(cameras => {
                const cameraSelect = document.getElementById('camera_list');
                cameraSelect.innerHTML = '';
                cameras.forEach(camera => {
                    const option = document.createElement('option');
                    option.value = camera.index;
                    option.textContent = `${camera.name} (Index: ${camera.index})`;
                    cameraSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error fetching camera list:', error);
            });
    }

    function submitCameraProperties(properties) {
        return fetch('/set_camera_properties', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: properties,
        }).then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        }).then(data => {
            console.log('Camera properties updated:', data);
        }).catch(error => {
            console.error('Error updating camera properties:', error);
        });
    }


    
    function submitPID() {
        const ra_pid_p = document.getElementById('ra_pid_p').value;
        const ra_pid_i = document.getElementById('ra_pid_i').value;
        const ra_pid_d = document.getElementById('ra_pid_d').value;
        document.getElementById('ra_pid_p_value').textContent = ra_pid_p;
        document.getElementById('ra_pid_i_value').textContent = ra_pid_i;
        document.getElementById('ra_pid_d_value').textContent = ra_pid_d;

        const dec_pid_p = document.getElementById('dec_pid_p').value;
        const dec_pid_i = document.getElementById('dec_pid_i').value;
        const dec_pid_d = document.getElementById('dec_pid_d').value;
        document.getElementById('dec_pid_p_value').textContent = dec_pid_p;
        document.getElementById('dec_pid_i_value').textContent = dec_pid_i;
        document.getElementById('dec_pid_d_value').textContent = dec_pid_d;

        fetch('/set_pid', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ ra_pid_p, ra_pid_i, ra_pid_d, dec_pid_p, dec_pid_i, dec_pid_d }),
        })
    }



    function acquire() {
        fetch('/acquire', { method: 'POST' })
            .then(response => console.log('Acquisition triggered'))
            .catch(error => console.error('Acquisition error:', error));
    }
    
    function resetCentroids(done) {
        fetch('/reset_centroids', { method: 'POST' })
            .then(response => {
                console.log('Centroids reset to current star positions');
                if (done) done();
            })
            .catch(error => console.error('Reset centroids error:', error));
    }

    function clearCentroids(done) {
        fetch('/clear_centroids', { method: 'POST' })
            .then(response => {
                console.log('Centroids cleared');
                if (done) done();
            })
            .catch(error => console.error('Clear centroids error:', error));
    }

    function calibrate(with_backlash) {
        fetch('/calibrate', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: `with_backlash=${with_backlash}`
        })                
        .then(response => response.text())
        .then(data => {
            document.getElementById('pec_table_text').value = data;
        })
        .catch(error => {
            document.getElementById('pec_table_text').value = 'Error: ' + error;
        });
    }


    function saveFrame() {
        fetch('/save_frame', {
            method: 'POST',
        })
        .then(response => {
            if (response.ok) {
                return response.blob(); // Convert the response to a Blob
            } else {
                return response.json().then(data => {
                    throw new Error(data.message || 'Failed to save frame');
                });
            }
        })
        .then(blob => {
            // Create a temporary link element
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'saved_frame.png'; // Set the file name
            document.body.appendChild(a);
            a.click(); // Trigger the download
            a.remove(); // Remove the link element
            window.URL.revokeObjectURL(url); // Revoke the object URL
        })
        .catch(error => {
            console.error('Error:', error);
            alert('Error: ' + error.message);
        });
    }