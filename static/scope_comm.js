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


    function setPier(pier) {
        scopeSubmitJSON("/set_pier", { pier: pier });
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


    function submitGuideInterval() {
        const guide_interval = document.getElementById('guide_interval').value;
        document.getElementById('guide_interval_value').textContent = guide_interval;
        document.getElementById('guide_interval_auto').textContent = Number(guide_interval) === 0 ? 'auto' : '';
        submitSetting("guide_interval", guide_interval);
    }
    
    function submitGuideArcsec() {
        const guide_arcsec = document.getElementById('guide_arcsec').value;
        document.getElementById('guide_arcsec_value').textContent = guide_arcsec;
        submitSetting("guide_arcsec", guide_arcsec);
    }

    function submitGuideMethod(value, axis) {
        submitSetting("guide_method", value, axis);
    }
    
    
    function setLabelValue(label, value) {
        if (label.tagName === 'INPUT') {
            if (document.activeElement !== label) label.value = value;
        } else {
            label.textContent = value;
        }
    }

    function setPidFromInput(id) {
        const box = document.getElementById(id + '_value');
        const slider = document.getElementById(id);
        const value = parseFloat(box.value);
        if (isNaN(value) || value < 0) {
            box.value = slider.value;
            return;
        }
        if (value > parseFloat(slider.max)) slider.max = value;
        slider.value = value;
        submitPID();
    }

    function submitPID() {
        const ra_pid_p = document.getElementById('ra_pid_p').value;
        const ra_pid_i = document.getElementById('ra_pid_i').value;
        const ra_pid_d = document.getElementById('ra_pid_d').value;
        setLabelValue(document.getElementById('ra_pid_p_value'), ra_pid_p);
        setLabelValue(document.getElementById('ra_pid_i_value'), ra_pid_i);
        setLabelValue(document.getElementById('ra_pid_d_value'), ra_pid_d);

        const dec_pid_p = document.getElementById('dec_pid_p').value;
        const dec_pid_i = document.getElementById('dec_pid_i').value;
        const dec_pid_d = document.getElementById('dec_pid_d').value;
        setLabelValue(document.getElementById('dec_pid_p_value'), dec_pid_p);
        setLabelValue(document.getElementById('dec_pid_i_value'), dec_pid_i);
        setLabelValue(document.getElementById('dec_pid_d_value'), dec_pid_d);

        fetch('/set_pid', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ ra_pid_p, ra_pid_i, ra_pid_d, dec_pid_p, dec_pid_i, dec_pid_d }),
        })
    }



    function submitTau() {
        const error_filter_tau = document.getElementById('error_filter_tau').value;
        document.getElementById('error_filter_tau_value').textContent = error_filter_tau;
        fetch('/autoguider_set_tau', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ error_filter_tau }),
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