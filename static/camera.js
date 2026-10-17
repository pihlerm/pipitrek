    function submitCameraControl(name, value) {
        fetch('/set_direct_camera_control', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ "name" : name, "value" : value }),
        })
        .then(response => console.log(`Camera control ${name} set to ${value}`))
        .catch(error => console.error(`Error setting camera control ${name}:`, error));
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




    function loadCameraControls() {
        fetch('/get_camera_controls')
        .then(response => response.json())
        .then(data => {
            const cameraPanel = document.getElementById('camera_panel');

            const rows = cameraPanel.querySelectorAll('tr'); // Get all rows in the camera panel

            rows.forEach(row => {
                if (row.dynamic) {
                    row.remove(); // Remove the row if it has the dynamic property
                }
            });

            for (const [property, details] of Object.entries(data)) {
                const row = document.createElement('tr');
                row.className = 'controller-row';
                row.dynamic = true;

                const labelCell = document.createElement('td');
                labelCell.innerHTML = `<label for="${property}">${property.replace(/_/g, ' ')}:</label>`;
                row.appendChild(labelCell);

                const controlCell = document.createElement('td');
                

                if (details.type === 'int') {
                    // Create a slider for integer properties
                    if(property === "exposure_time_absolute") {
                        input_min = 0;
                        input_max = Math.log(details.max)/Math.log(Math.sqrt(2))+0.1;
                        value = Math.log(details.value)/Math.log(Math.sqrt(2));
                        controlCell.innerHTML = `
                        <input type="range" class="normal-range" id="${property}" name="${property}" 
                            min="${input_min}" max="${input_max}" step="0.1"
                            value="${value}" 
                            oninput="updateExposure('${property}', this.value, ${details.max})"
                            onchange="submitCameraControl( '${property}', document.getElementById('exposure_time_absolute_value').textContent)">
                        <span id="${property}_value">${details.value}</span>`;
                    } else {
                        controlCell.innerHTML = `
                        <input type="range" class="normal-range" id="${property}" name="${property}" 
                            min="${details.min}" max="${details.max}" step="${details.step}" 
                            value="${details.value}" 
                            oninput="updateLabel('${property}', this.value)"
                            onchange="submitCameraControl('${property}', this.value)">
                        <span id="${property}_value">${details.value}</span>`;
                    }
                } else if (details.type === 'bool') {
                    // Create a checkbox for boolean properties
                    controlCell.innerHTML = `
                        <input type="checkbox" id="${property}" name="${property}" 
                            ${details.value ? 'checked' : ''} 
                            onchange="submitCameraControl('${property}', this.checked ? 1 : 0)">
                    `;
                } else if (details.type === 'menu') {
                    // Create radio buttons for menu properties
                    const options = Object.entries(details.options)
                        .map(([key, label]) => `
                            <input type="radio" id="${property}_${key}" name="${property}" value="${key}" 
                                ${details.value == key ? 'checked' : ''} 
                                onchange="submitCameraControl('${property}', ${key})">
                            <label for="${property}_${key}">${label}</label>
                        `);//.join('<br>');
                    controlCell.innerHTML = options;
                }

                row.appendChild(controlCell);
                cameraPanel.appendChild(row);
            }

            // blank row
            const row = document.createElement('tr');
            row.innerHTML="<td></td><td></td>"
            cameraPanel.appendChild(row);


        })
        .catch(error => console.error('Error fetching camera properties:', error));
    }

    // Updates values of the already created camera control elements, without creating new ones
    function updateCameraControls() {
        return fetch('/get_camera_controls')
        .then(response => response.json())
        .then(data => {
            for (const [property, details] of Object.entries(data)) {
                if (details.type === 'int') {
                    if (property === "exposure_time_absolute") {
                        const sliderValue = Math.log(details.value) / Math.log(Math.sqrt(2));
                        setSliderFromServer(property, sliderValue, details.value);
                    } else {
                        setSliderFromServer(property, details.value);
                    }
                } else if (details.type === 'bool') {
                    const checkbox = document.getElementById(property);
                    if (checkbox) {
                        checkbox.checked = !!details.value;
                    }
                } else if (details.type === 'menu') {
                    const radio = document.getElementById(`${property}_${details.value}`);
                    if (radio) {
                        radio.checked = true;
                    }
                }
            }
        })
        .catch(error => console.error('Error updating camera controls:', error));
    }

    function updateExposure(property, value, max_value) {
        const exposure = Math.min(Math.pow(Math.sqrt(2), value), max_value);
        const label = document.getElementById(`${property}_value`);

        if (label) {
            label.textContent = exposure.toFixed(0); // Update label
        }
    }

    let cameraPropertiesRefreshInterval = null;

    function startCameraPropertiesRefresh() {
        if (cameraPropertiesRefreshInterval !== null) {
            return;
        }

        refreshCameraProperties();
        cameraPropertiesRefreshInterval = setInterval(refreshCameraProperties, 3000);
    }

    function stopCameraPropertiesRefresh() {
        if (cameraPropertiesRefreshInterval !== null) {
            clearInterval(cameraPropertiesRefreshInterval);
            cameraPropertiesRefreshInterval = null;
        }
    }

    function refreshCameraProperties() {
        fetch('/get_camera_properties', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
        })
        .then(response => response.json())
        .then(data => {
            if (!data || data.status=='error') {
                console.error('Error fetching camera properties:', data ? data.status : 'No data');
            } else {
                updateCameraProperties(data);
            }
        })
        .catch(error => console.error('Error refreshing camera properties:', error));

        updateCameraControls();
    }

    function updateCameraProperties(data) {

        if(!data || data === null) {
            return;
        }
        
        setSliderFromServer('rotation_angle', data.rotation_angle.toFixed(3));
        rotation_angle=data.rotation_angle;
        updateSkyMapRotation(data.rotation_angle);
        setSliderFromServer('pixel_scale', data.pixel_scale);
        setSliderFromServer('integrate_frames', data.integrate_frames);
        setSliderFromServer('r_channel', data.r_channel);
        setSliderFromServer('g_channel', data.g_channel);
        setSliderFromServer('b_channel', data.b_channel);

        setSliderFromServer('camera_exposure', data.exposure);

        const cameraList = document.getElementById('camera_list');
        if (cameraList) {
            cameraList.value = data.camera_index;
        }

        // Set the camera FPS radio button
        const fpsRadio = document.querySelector(`input[name="camera-fps"][value="${data.camera_fps}"]`);
        if (fpsRadio) {
            fpsRadio.checked = true;
        }

        // Set the resolution radio button
        const resolutionRadio = document.querySelector(`input[name="resolution"][value="${data.resolution.width}x${data.resolution.height}"]`);
        if (resolutionRadio) {
            resolutionRadio.checked = true;
        }

        // Set the video mode radio button
        const videoModeRadio = document.querySelector(`input[name="video-mode"][value="${data.video_mode}"]`);
        if (videoModeRadio) {
            videoModeRadio.checked = true;
        }

        // Set the camera color radio button
        const colorRadioButton = document.querySelector(`input[name="camera_color"][value="${data.camera_color}"]`);
        if (colorRadioButton) {
            colorRadioButton.checked = true;
        }

        // Update the camera_info element
        const cameraInfo = document.getElementById('camera_info');
        if (cameraInfo) {
            cameraInfo.textContent = `FPS:${data.camera_fps} ${data.video_mode} ${data.resolution.width}x${data.resolution.height} exposure:${data.exposure_ms}ms frame time:${data.last_frame_time.toFixed(2)}s`;
        }
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

    function submitRotationAngle() {
        const rotation_angle = document.getElementById('rotation_angle').value;
        document.getElementById('rotation_angle_value').textContent = rotation_angle;
        submitCameraProperties(JSON.stringify({ "rotation_angle" : rotation_angle }));
    }

    function submitPixelScale() {
        const pixel_scale = document.getElementById('pixel_scale').value;
        document.getElementById('pixel_scale_value').textContent = pixel_scale;
        submitCameraProperties(JSON.stringify({ "pixel_scale" : pixel_scale }));
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
