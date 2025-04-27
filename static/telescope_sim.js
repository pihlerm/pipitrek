class TelescopeSim {
    constructor(canvas, longitude = 14.5058, latitude = 46.0569) {
        this.canvas = canvas;
        this.latitude = latitude * Math.PI / 180; // Convert to radians
		this.longitude = longitude; // Keep in degrees
        this.westPier = false;
		this.telescopeScale = 0.5;
        this.raAngle = 0;
        this.decAngle = 0;
        this.raAngleTarget = 0;
        this.decAngleTarget = 0;
        this.onSelectCallback = null;
        this.currentObjectIndex = null;

        this.addRotation = 0;

        this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false });
        //this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio); // Optimize for Quest 3
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.clock = new THREE.Clock();

        this.addSceneAndLighting();

        this.controllerLeft = null;
        this.controllerRight = null;

        this.addGround(); 
        this.addSkyPoles();
        this.addTelescope();
        this.addOrbitControls();
        this.addControllers();
        this.addClickDetection();
        this.addMusic();
        //this.addCoordinateAxes(this.scene);


        // Initial angles
        this.setAngles(this.raAngle, this.decAngle);

        // Start animation
        this.renderer.setAnimationLoop(() => this.animate()); 
        //this.animate();
    }    

    onSelect(funct) {
        this.onSelectCallback = funct;
    }

    addOrbitControls() {
        // OrbitControls
        this.controls = new THREE.OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 1;
        this.controls.maxDistance = 50;
        this.controls.enablePan = true;        
    }
    
    animateToAngles(ra, dec) {
		if(this.westPier) {
            ra = (ra + 180) % 360;
            dec = 180 - dec;
        }
        while (dec > 180) dec -= 360;
        while (dec < -180) dec += 360;
        this.raAngleTarget = ra;
        this.decAngleTarget = dec;
    
    }

    setAngles(ra, dec) {
		if(this.westPier) {
            ra = (ra + 180) % 360;
            dec = 180 - dec;
        }
        while (dec > 180) dec -= 360;
        while (dec < -180) dec += 360;
        this.raAngle = ra;
        this.decAngle = dec;
        this.raAngleTarget = ra;
        this.decAngleTarget = dec;
    }

    meridianFlip() {
        this.raAngle = (this.raAngle + 180) % 360;
        const decRot = Math.sign(this.decAngle) * (180 - 2 * Math.abs(this.decAngle));
        this.decAngle += decRot;
        this.westPier = !this.westPier;
        this.setAngles(this.raAngle, this.decAngle);
    }
    setPier(west = false) {
        this.westPier = west;
    }

    parseRA(raStr) {
        const [hours, minutes, seconds] = raStr.split(':').map(Number);
        return hours + minutes / 60 + seconds / 3600;
    }

    parseDec(decStr) {
        const match = decStr.match(/([+-]?\d+)\*(\d+):(\d+)/);
        if (!match) return 0;
        const degrees = parseInt(match[1]);
        const minutes = parseInt(match[2]);
        const seconds = parseInt(match[3]);
        const sign = degrees >= 0 ? 1 : -1;
        return degrees + sign * (minutes / 60 + seconds / 3600);
    }

    getJulianDate(now) {
        const year = now.getUTCFullYear();
        const month = now.getUTCMonth() + 1;
        const day = now.getUTCDate();
        const hours = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600;
        let y = year, m = month;
        if (m <= 2) {
            y -= 1;
            m += 12;
        }
        const A = Math.floor(y / 100);
        const B = 2 - A + Math.floor(A / 4);
        const JD0 = Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + day + B - 1524.5;
        return JD0 + hours / 24;
    }

    HoursMinutesSeconds(time) {
        function frac(X) {
            X = X - Math.floor(X);
            if (X<0) X = X + 1.0;
            return X;		
        }
   
        var h = Math.floor(time);
        var min = Math.floor(60.0*frac(time));
        var secs = Math.round(60.0*(60.0*frac(time)-min));
        var str;
        if (min>=10) str=h+":"+min;
        else  str=h+":0"+min;
        if (secs<10) str = str + ":0"+secs;
        else str = str + ":"+secs;
        return " " + str;       
     }
       

    calculateLST(longitudeDegrees) {
        const now = new Date(); // browser time (assumed UTC or converted below)
        const JD = this.getJulianDate(now);
        const T = (JD - 2451545.0) / 36525.0;
    
        // Calculate Greenwich Mean Sidereal Time (GMST) in seconds
        let GMST = 280.46061837 +
                   360.98564736629 * (JD - 2451545) +
                   0.000387933 * T * T -
                   (T * T * T) / 38710000;
    
        // Normalize to 0–360
        GMST = ((GMST % 360) + 360) % 360;
    
        // Local Sidereal Time
        let LST = GMST + longitudeDegrees;
    
        // Normalize to 0–360
        LST = ((LST % 360) + 360) % 360;
    
        // Convert to hours
        return LST / 15;
    }
    
    
    pointTelescope(raStr, decStr, animate=false) {
        const raHours = this.parseRA(raStr);
        const decDegrees = this.parseDec(decStr);
        const lstHours = this.calculateLST(this.longitude);
        let raDiff = (raHours - lstHours) * 15 + 180;
        raDiff = ((raDiff % 360) + 360) % 360;
        if(animate) {
            this.animateToAngles(raDiff, decDegrees);
        } else {
            this.setAngles(raDiff, decDegrees);
        }
    }

    resize(width, height) {
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate() {
        //requestAnimationFrame(() => this.animate());
        
        // Update starfield rotation based on current LST
        const currentLST = this.calculateLST(this.longitude);
        this.starfieldGroup.rotation.y = -currentLST / 12 * Math.PI - this.addRotation;

        
        const elapsedTime = this.clock.getElapsedTime();
        this.starMaterial.uniforms.uTime.value = elapsedTime;

        const delta = 0.2;
        if(this.raAngle !== this.raAngleTarget) {
            var move = delta;
            if(Math.abs(this.raAngleTarget-this.raAngle > 180)) {
                move = -delta;
            }
            this.raAngle += Math.sign(this.raAngleTarget-this.raAngle) * move;
            if(this.raAngle>360) this.raAngle -= 360;
            if(this.raAngle<0) this.raAngle += 360;
            if (Math.abs(this.raAngle - this.raAngleTarget) < 2*delta) {
                this.raAngle = this.raAngleTarget;
            }
        }
        if(this.decAngle !== this.decAngleTarget) {
            this.decAngle += Math.sign((this.decAngleTarget-this.decAngle)) * delta;
            if (Math.abs(this.decAngle - this.decAngleTarget) < 2*delta) {
                this.decAngle = this.decAngleTarget;
            }
        }
        this.raGroup.rotation.y = this.raAngle * Math.PI / 180 - this.addRotation;
        this.decGroup.rotation.z = this.decAngle * Math.PI / 180;
        
        this.handleControllers();

        if (this.renderer.xr.isPresenting) {
            this.renderer.render(this.scene, this.camera);
        } else {
            if(this.controls) this.controls.update();
            this.renderer.render(this.scene, this.camera);
        }
    }

    handleControllers() {
        if (this.rightController && this.rightGamepad) {
            const gp = this.rightGamepad;
        
            // Thumbstick axes
            const x = gp.axes[2] || 0;  // Left/right on thumbstick
            const y = gp.axes[3] || 0;  // Up/down on thumbstick
        
            if (Math.abs(x) > 0.1 || Math.abs(y) > 0.1) {
                this.addRotation += x * 0.02; // Adjust rotation speed as needed
            }
        
            // Oculus A button
            if (gp.buttons[4].pressed && !this.aPressed) {
                this.aPressed = true;
                if(this.currentObjectIndex == null || typeof this.starCatalog === 'undefined' || this.starCatalog==null) {
                    this.userRig.position.set(0, 0, 0);
                    return;
                }
                const [raStr, decStr, mag] = this.starCatalog[this.currentObjectIndex];
                const [x, y, z] =  this.positionFromRADEC(raStr, decStr, 90, true);
                this.removeCurrentLabel();
                this.currentObjectIndex = null;
                this.userRig.position.set(x, y, z);    
            } else if (!gp.buttons[4].pressed) {
                this.aPressed = false;
            }

            // Oculus B button
            if (gp.buttons[5].pressed) {
                //this.userRig.position.set(0, 0, 0);    
            }
        }
    }

    positionFromRADEC(raStr, decStr, r=100, world=false) {
        const ra = this.parseRA(raStr)/12 * Math.PI; // Hours to radians
        const dec = this.parseDec(decStr)/180 * Math.PI; // Degrees to radians
        return this.positionFromRADECrad(ra, dec, r, world);
    }

    positionFromRADECrad(ra, dec, r=100, world=false) {
        // Set position
        var pos = [];
        pos[0] = -r * Math.cos(ra)*Math.cos(dec); // -x
        pos[1] = r * Math.sin(dec); // y
        pos[2] = r * Math.sin(ra) * Math.cos(dec); // z
        if(world) {
            const v = new THREE.Vector3(pos[0], pos[1], pos[2]);
            this.starfieldGroup.updateMatrixWorld(true);
            v.applyMatrix4(this.starfieldGroup.matrixWorld);
            pos[0] = v.x;
            pos[1] = v.y;
            pos[2] = v.z;
        }
        return pos;
    }

    addStarfield(starCatalog, minMagnitude = 5) {
        
        if (typeof starCatalog === 'undefined') return this.addRandomStars();

        // Starfield
        const starGeometry = new THREE.BufferGeometry();
        if(this.starCatalog == null) this.starCatalog = [];
        this.starCatalog = this.starCatalog.concat(starCatalog.filter(star => {
            const mag = star[2];
            return mag <= minMagnitude; // Filter stars by magnitude
        }));
        
        const starCount = this.starCatalog.length;
        const starPositions = new Float32Array(starCount * 3);
        const starSizes = new Float32Array(starCount); // Array for per-star sizes
        const r = 105;
        const maxMag = 6.5; // Faintest magnitude for size scaling
        const baseSize = 1; // Minimum size for faint stars
        const sizeScale = 0.5; // Scale factor for size variation

        for (let i = 0; i < starCount; i++) {
            const [raStr, decStr, mag] = this.starCatalog[i];           
            const [x, y, z] = this.positionFromRADEC(raStr, decStr, r);
            starPositions.set([x, y, z], i * 3);
            // Set size based on magnitude
            starSizes[i] = baseSize + sizeScale * (maxMag - mag);
        }
        starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
        starGeometry.setAttribute('size', new THREE.BufferAttribute(starSizes, 1));

        // Custom ShaderMaterial to use per-star sizes
        this.starMaterial = new THREE.ShaderMaterial({
            uniforms: {
                color: { value: new THREE.Color(0xffffff) },
                pointTexture: { value: this.createStarTexture() },
                uTime: { value: 0.0 }
            },
            vertexShader: `
                attribute float size;
                varying float vSize;
                varying vec3 vColor;
                uniform float uTime;
                varying float vTwinkle;

                void main() {
                    vColor = vec3(1.0);
                    vTwinkle = sin(position.x * 0.5 + uTime * 2.0) * 0.2 + 0.8; // Twinkle effect based on position and time
                    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
                    vSize = size;
                    gl_PointSize = size * (300.0 / -mvPosition.z);
                    gl_Position = projectionMatrix * mvPosition;
                }
            `,
            fragmentShader: `
                uniform vec3 color;
                uniform sampler2D pointTexture;
                uniform float uTime;
                varying float vSize;
                varying vec3 vColor;
                varying float vTwinkle;

                void main() {
                    vec4 texColor = texture2D(pointTexture, gl_PointCoord);
        
                    if (texColor.a < 0.1) discard;
        
                    // Fade small stars
                    float fade = smoothstep(1.0, 3.0, vSize);
        
                    gl_FragColor = vec4(color * vColor, texColor.a * fade * vTwinkle);
                }
            `,
            blending: THREE.AdditiveBlending, // makes stars "glow" together
            transparent: true,
            depthTest: true
        });

        const starfield = new THREE.Points(starGeometry, this.starMaterial);
        this.starfieldGroup.add(starfield);
    }

    createStarTexture() {
        const size = 32;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const context = canvas.getContext('2d');
    
        // Draw radial gradient
        const gradient = context.createRadialGradient(
            size / 2, size / 2, 0,
            size / 2, size / 2, size / 2
        );
        gradient.addColorStop(0, 'rgba(255, 255, 255, 1)');
        gradient.addColorStop(0.2, 'rgba(255, 255, 255, 0.6)');
        gradient.addColorStop(0.4, 'rgba(255, 255, 255, 0.2)');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
    
        context.fillStyle = gradient;
        context.fillRect(0, 0, size, size);
    
        const texture = new THREE.CanvasTexture(canvas);
        return texture;
    }

    addRandomStars(starCount = 1000) {
        const starGeometry = new THREE.BufferGeometry();
        const starPositions = new Float32Array(starCount * 3);
        for (let i = 0; i < starCount * 3; i += 3) {
            const theta = Math.random() * 2 * Math.PI;
            const phi = Math.acos(2 * Math.random() - 1);
            const r = 100; // Large sphere radius
            starPositions[i] = r * Math.sin(phi) * Math.cos(theta);
            starPositions[i + 1] = r * Math.sin(phi) * Math.sin(theta);
            starPositions[i + 2] = r * Math.cos(phi);
        }
        starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
        const starMaterial = new THREE.PointsMaterial({
            color: 0xffffff,
            size: 0.1,
            sizeAttenuation: true
        });    
        const starfield = new THREE.Points(starGeometry, starMaterial);
        this.starfieldGroup.add(starfield);
    }


    addImage(img, name, ra, dec, arcsecondsPerPixel, rotation = 0) {
        const catalogIndex = this.starCatalog.length;
        if(name==="Luna") {
            ra = this.HoursMinutesSeconds(this.calculateLST(this.longitude));
        }

        this.starCatalog.push([ra, dec, 1, name, "", ""]);
    
        const r = 100;
    
        // Load texture
        const texture = new THREE.TextureLoader().load(img, (texture) => {
            // Now that texture is loaded, we know its size
            const imageWidth = texture.image.width;
            const imageHeight = texture.image.height;
    
            // Total size in arcseconds
            // Convert to radians
            const widthRad = THREE.MathUtils.degToRad(imageWidth * arcsecondsPerPixel / 3600);
            const heightRad = THREE.MathUtils.degToRad(imageHeight * arcsecondsPerPixel / 3600);
    
            // Create sphere segment
            const sphereSegment = new THREE.SphereGeometry(
                r, 32, 32,
                Math.PI/2 - widthRad/2, widthRad,
                Math.PI/2 - heightRad/2, heightRad
            );
    
            // Create material
            const material = new THREE.MeshBasicMaterial({
                map: texture,
                side: THREE.DoubleSide
            });
    
            // Create mesh
            const segmentMesh = new THREE.Mesh(sphereSegment, material);
            segmentMesh.userData.index = catalogIndex;
    
            // Position
            const [x, y, z] = this.positionFromRADEC(ra, dec);
            segmentMesh.position.set(0, 0, 0);
    
            // Rotate toward RA/Dec
            const target = new THREE.Vector3(x, y, z);
            segmentMesh.lookAt(target);
    
            // Adjust if needed
            segmentMesh.rotateZ(rotation); // your rotation tweak
    
            this.starfieldGroup.add(segmentMesh);
        });
    }

    addClickDetection() {
        // Initialize raycaster
        this.raycaster = new THREE.Raycaster();
        this.raycaster.params.Points.threshold = 5; // Adjust for starfield point sensitivity
    
        // Track current label
        this.currentLabel = null;
    
        // Mouse position vector for non-VR
        const mouse = new THREE.Vector2();
    
        // Mouse click handler
        const onClick = (event) => {
            mouse.x = (event.clientX / this.canvas.clientWidth) * 2 - 1;
            mouse.y = -(event.clientY / this.canvas.clientHeight) * 2 + 1;
            this.raycaster.setFromCamera(mouse, this.camera);
            this.handleRaycast();
        };
        const onDblClick = (event) => {
            mouse.x = (event.clientX / this.canvas.clientWidth) * 2 - 1;
            mouse.y = -(event.clientY / this.canvas.clientHeight) * 2 + 1;
            this.raycaster.setFromCamera(mouse, this.camera);
            this.handleRaycast();
            if(this.currentObjectIndex == null || typeof this.starCatalog === 'undefined' || this.starCatalog==null) return;
            const [raStr, decStr, mag] = this.starCatalog[this.currentObjectIndex];
            const [x, y, z] =  this.positionFromRADEC(raStr, decStr, 95, true);
            this.camera.position.set(x, y, z);
            const [x1, y1, z1] =  this.positionFromRADEC(raStr, decStr, 100, true);
            this.camera.lookAt(x1, y1, z1);
            this.camera.updateProjectionMatrix();
        };
    

        // Add mouse event listener for non-VR
        this.canvas.addEventListener('click', onClick, false);
        this.canvas.addEventListener('dblclick', onDblClick, false);
        
    
    }

    createTextSprite(text, width=512, height=64) {
        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        canvas.width = width; // Increased for longer text
        canvas.height = height;
        context.font = 'Bold 28px Arial'; // Slightly smaller font for fit
        context.fillStyle = 'rgba(0, 0, 0, 0.7)'; // Semi-transparent black background
        context.fillRect(0, 0, canvas.width, canvas.height); // Background for contrast
        context.fillStyle = 'white'; // White text
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(text, canvas.width / 2, canvas.height / 2); // Center text
        const texture = new THREE.CanvasTexture(canvas);
        const spriteMaterial = new THREE.SpriteMaterial({ map: texture });
        const sprite = new THREE.Sprite(spriteMaterial);
        return sprite;
    }

    removeCurrentLabel() {
        if (this.currentLabel) {
            this.scene.remove(this.currentLabel);
            this.currentLabel = null;
        }
    }

    addCurrentLabel(point, labelText) {
         // Create and position new label
        const labelSprite = this.createTextSprite(labelText);
        labelSprite.scale.set(20, 4, 4); // Reduced scale for clarity
        labelSprite.position.copy(point);
        labelSprite.position.x += 0.5; // Offset for visibility
        this.scene.add(labelSprite);
        this.currentLabel = labelSprite;
    }
    
    // Shared raycast logic
    handleRaycast() {
        const intersects = this.raycaster.intersectObjects([this.starfieldGroup], true);
        if (intersects.length > 0) {
            const intersect = intersects[0];
            const point = intersect.point;
            let index = null;
            if(intersect.object.isPoints) {
                index = intersect.index;
            } else {
                index = intersect.object.userData.index;
            }
            if (index != null && typeof this.starCatalog !== 'undefined') {
                const star = this.starCatalog[index];
                const [raStr, decStr, mag, name, constellation, HDnr] = star;
                const labelText = `${name} ${constellation} HD${HDnr} ${mag}`;
                console.log(`Selected star: RA=${raStr}, Dec=${decStr}, Label=${labelText}, Position=${point.x},${point.y},${point.z}`);

                // Remove previous label
                this.removeCurrentLabel();
                this.addCurrentLabel(point, labelText);

                this.currentObjectIndex = index; // Store the index of the selected object
                if(this.onSelectCallback) this.onSelectCallback(index);
            }
        } else {
            // Remove label if no star selected
            if (this.currentLabel) {
                this.scene.remove(this.currentLabel);
                this.currentLabel = null;
            }
            this.currentObjectIndex = null;
            if(this.onSelectCallback) this.onSelectCallback(null);
            console.log('No star selected');
        }
    }


    addControllers() {
        // Prepare controller slots
        const controller0 = this.renderer.xr.getController(0);
        const controller1 = this.renderer.xr.getController(1);

        // VR controller handler
        const onSelect = () => {
            if(this.rightController == null) return;
            const controller = this.rightController;
            // Make sure matrices are updated
            controller.updateMatrixWorld(true);
            // Get world position
            const position = new THREE.Vector3();
            controller.getWorldPosition(position);
            this.raycaster.set(position, controller.getWorldDirection(new THREE.Vector3()).negate());
            this.raycaster.camera = this.renderer.xr.getCamera(this.camera);
            this.handleRaycast();
        };

        const onSqueeze = () => {
            if(this.currentObjectIndex == null || typeof this.starCatalog === 'undefined' || this.starCatalog==null) return;
            const star = this.starCatalog[this.currentObjectIndex];
            const [raStr, decStr, mag] = star;
            this.pointTelescope(raStr, decStr, true);
        };


        // Handle when controllers connect
        const onControllerConnected = (event) => {
            const handedness = event.data.handedness;
            const controller = event.target;

            if (handedness === 'right') {
                console.log('Right controller connected!');
                controller.addEventListener('select', onSelect);
                controller.addEventListener('squeeze', onSqueeze);
                

                this.rightController = controller;
                this.rightGamepad = event.data.gamepad || null; // <-- store gamepad reference!

                // Create laser
                const laserGeometry = new THREE.CylinderGeometry(0.002, 0.002, 100, 8);
                const laserMaterial = new THREE.MeshBasicMaterial({ color: 0xff0000 });

                const laser = new THREE.Mesh(laserGeometry, laserMaterial);

                // Rotate so it's pointing forward
                laser.rotation.x = Math.PI / 2;

                // Move the laser so it starts at the controller
                laser.position.z = -50; // Half of 100 meters forward

                // Attach laser to controller
                controller.add(laser);

                this.userRig.add(controller);
            }
        }

        // Listen for connected event on both controller slots
        controller0.addEventListener('connected', onControllerConnected);
        controller1.addEventListener('connected', onControllerConnected);
        
    }



    enableWebXR() {
        // Enable WebXR on renderer
        this.renderer.xr.enabled = true;
       
        this.camera = new THREE.PerspectiveCamera(70, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);

        this.userRig = new THREE.Group();
        this.userRig.add(this.camera);
        this.scene.add(this.userRig);
        
        // Adjust camera for VR
        this.camera.position.set(0, 0, 0);
        this.userRig.position.set(0, 0, 0); // Eye-level height for VR
        this.userRig.near = 0.1; // Adjust near plane for VR
        this.userRig.far = 1000; // Ensure far plane covers starfield
        //this.camera.updateProjectionMatrix();

    
        // Disable OrbitControls in VR (optional, as VR uses headset orientation)
        this.renderer.xr.addEventListener('sessionstart', () => {
            this.controls.enabled = false;
        });
        this.renderer.xr.addEventListener('sessionend', () => {
            this.controls.enabled = true;
        });
    }

    enterVR() {
        this.renderer.xr.getSession()?.end(); // End any existing session
        navigator.xr.requestSession('immersive-vr', {
            optionalFeatures: ['local-floor', 'bounded-floor']
        }).then(session => {
            this.renderer.xr.setSession(session);
            session.addEventListener('end', () => {
            });
        }).catch(err => {
            console.error('Failed to start VR session:', err);
        });        
    }


    addSceneAndLighting() {
        // Scene setup
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(30, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
        //this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        this.camera.position.set(5, 5, 10);
        this.camera.lookAt(0, 0, 0);
        // Lighting
        this.ambientLight = new THREE.AmbientLight(0x404040, 0.6);
        this.scene.add(this.ambientLight);
        this.directionalLight = new THREE.DirectionalLight(0xffffff, 1.2);
        this.directionalLight.position.set(5, 5, 5);
        this.scene.add(this.directionalLight);

        this.directionalLight2 = new THREE.DirectionalLight(0xffffff, 1.2);
        this.directionalLight2.position.set(0, 10, 0);
        this.scene.add(this.directionalLight2);

        // Groups
        this.starfieldGroup = new THREE.Group();
        this.starfieldPolarGroup = new THREE.Group();
        this.scene.add(this.starfieldPolarGroup);
        this.starfieldPolarGroup.add(this.starfieldGroup);
        this.starfieldPolarGroup.rotation.z = -(Math.PI / 2 - this.latitude);

    }

    addTelescope() {

        // Materials
        this.bodyMaterial = new THREE.MeshPhongMaterial({ color: 0x2222aa, shininess: 50 });
        this.axisMaterial = new THREE.MeshPhongMaterial({ color: 0xff0000, shininess: 50 });
        const laserMaterial = new THREE.LineBasicMaterial({ color: 0xff0000 }); 
        this.shaftMaterial = new THREE.MeshPhongMaterial({ color: 0x555555, shininess: 50 });
        this.weightMaterial = new THREE.MeshPhongMaterial({ color: 0x333333, shininess: 50 });
        const textureLoader = new THREE.TextureLoader();
        const telescopeTexture = textureLoader.load('PIPITREK.PNG');
        this.telescopeMaterial = new THREE.MeshPhongMaterial({
            map: telescopeTexture,
            shininess: 50,
            side: THREE.DoubleSide
        });
        this.telescopeBackMaterial = new THREE.MeshPhongMaterial({ color: 0x090909, shininess: 20 });


        // Dimensions
        const shaftHeight = 1.6*this.telescopeScale;
        const bodyL = 1.2*this.telescopeScale;
        const axleL = 1*this.telescopeScale;
        const shaftR = 0.2*this.telescopeScale;
        const smallShaftR = 0.05*this.telescopeScale;
        const smallShaftL = 2*this.telescopeScale;
        const smallShaftOffset = 0.5*this.telescopeScale;
        
        const axisR = 0.02*this.telescopeScale;
        const axisL = 3*this.telescopeScale;
        const weightR = 0.5*this.telescopeScale;
        const weightL = 0.2*this.telescopeScale;
        const weightOffset = 1*this.telescopeScale;

        const tubeR = 0.5*this.telescopeScale;
        const tubeL = 2*this.telescopeScale;
        const tubeOffset = -1*this.telescopeScale;
        
         

        this.polarGroup = new THREE.Group();
        this.scene.add(this.polarGroup);
        this.polarGroup.rotation.z = -(Math.PI / 2 - this.latitude);
        this.polarGroup.position.y = shaftHeight;

        this.raGroup = new THREE.Group();
        this.decGroup = new THREE.Group();
        //this.polarGroup.position.y = 1.6*this.telescopeScale;
        this.polarGroup.add(this.raGroup);
        this.raGroup.position.y = bodyL/2;
        this.raGroup.add(this.decGroup);


        // Vertical shaft
        const vshaftGeometry = new THREE.CylinderGeometry(shaftR, shaftR, shaftHeight, 32);
        const vshaft = new THREE.Mesh(vshaftGeometry, this.bodyMaterial);
        vshaft.position.y = shaftHeight / 2;
        this.scene.add(vshaft);


        // Polar axis - lower telescope body
        const raBodyGeometry = new THREE.CylinderGeometry(shaftR, shaftR, axleL, 32);
        const raBody = new THREE.Mesh(raBodyGeometry, this.bodyMaterial);
        const polarAxisGeometry = new THREE.CylinderGeometry(axisR, axisR, axisL, 32);
        const polarAxis = new THREE.Mesh(polarAxisGeometry, this.axisMaterial);
        this.polarGroup.add(raBody);
        //this.polarGroup.add(polarAxis);

        // Dec axis
        const decAxisGeometry = new THREE.CylinderGeometry(axisR, axisR, axisL, 32);
        const decAxis = new THREE.Mesh(decAxisGeometry, this.axisMaterial);
        decAxis.rotation.x = Math.PI / 2;
        const decBodyGeometry = new THREE.CylinderGeometry(shaftR, shaftR, axleL, 32);
        const decBody = new THREE.Mesh(decBodyGeometry, this.bodyMaterial);
        decBody.rotation.x = Math.PI / 2;
        this.raGroup.add(decBody);
        //this.raGroup.add(decAxis);

        // Counterweight shaft and weight
        const shaftGeometry = new THREE.CylinderGeometry(smallShaftR, smallShaftR, smallShaftL, 32);
        const shaft = new THREE.Mesh(shaftGeometry, this.shaftMaterial);
        shaft.rotation.x = Math.PI / 2;
        shaft.position.z = smallShaftOffset;

        const weightGeometry = new THREE.CylinderGeometry(weightR, weightR, weightL, 32);
        const weight = new THREE.Mesh(weightGeometry, this.weightMaterial);
        weight.rotation.x = Math.PI / 2;
        weight.position.z = weightOffset;

        const telescopeGeometry = new THREE.CylinderGeometry(tubeR, tubeR, tubeL, 32, 1, true);
        const telescope = new THREE.Mesh(telescopeGeometry, this.telescopeMaterial);
        telescope.rotation.z = Math.PI *3 / 2;
        telescope.position.z = tubeOffset;

        const telescopeBackGeometry = new THREE.CylinderGeometry(tubeR*1.1, tubeR*1.1, tubeL*0.1, 32);
        const telescopeBack = new THREE.Mesh(telescopeBackGeometry, this.telescopeBackMaterial);
        
        const laserGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(0, 0, tubeOffset),
            new THREE.Vector3(100, -bodyL/2, 0)
        ]);        
        const laser = new THREE.Line(laserGeometry, laserMaterial);

        telescopeBack.rotation.z = Math.PI / 2;
        telescopeBack.position.z = -tubeL/2;
        telescopeBack.position.x = -tubeL/2;
        this.decGroup.add(telescope);
        this.decGroup.add(telescopeBack);
        this.decGroup.add(shaft);
        this.decGroup.add(weight);
        this.decGroup.add(laser);
    }

    addCoordinateAxes(group) {
        // Materials for axes
        const xMaterial = new THREE.LineBasicMaterial({ color: 0xff0000 }); // Red for x
        const yMaterial = new THREE.LineBasicMaterial({ color: 0x00ff00 }); // Green for y
        const zMaterial = new THREE.LineBasicMaterial({ color: 0x0000ff }); // Blue for z
    
        // Geometries for axes (lines of length 5)
        const xGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(0, 0, 0),
            new THREE.Vector3(5, 0, 0)
        ]);
        const yGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(0, 0, 0),
            new THREE.Vector3(0, 5, 0)
        ]);
        const zGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(0, 0, 0),
            new THREE.Vector3(0, 0, 5)
        ]);
    
        // Create lines
        const xAxis = new THREE.Line(xGeometry, xMaterial);
        const yAxis = new THREE.Line(yGeometry, yMaterial);
        const zAxis = new THREE.Line(zGeometry, zMaterial);
    
        // Add axes to scene
        group.add(xAxis);
        group.add(yAxis);
        group.add(zAxis);
    
        // Add text labels at the end of each axis
        const xLabel = this.createTextSprite('X', 64, 64);
        xLabel.scale.set(1, 1, 1);
        xLabel.position.set(5.5, 0, 0); // Slightly beyond x-axis end
        const yLabel = this.createTextSprite('Y', 64, 64);
        yLabel.scale.set(1, 1, 1);
        yLabel.position.set(0, 5.5, 0); // Slightly beyond y-axis end
        const zLabel = this.createTextSprite('Z', 64, 64);
        zLabel.scale.set(1, 1, 1);
        zLabel.position.set(0, 0, 5.5); // Slightly beyond z-axis end
    
        // Add labels to scene
        group.add(xLabel);
        group.add(yLabel);
        group.add(zLabel);
    }    

    addSkyPoles() {
        // Materials for axes
        const mat = new THREE.LineBasicMaterial({ color: 0x00ff00 }); // Green for y
    
        // Add text labels at the end of each axis
        const nLabel = this.createTextSprite('N', 64, 64);
        nLabel.scale.set(10, 10, 10);
        nLabel.position.set(100, 0, 0);
        
        const sLabel = this.createTextSprite('S', 64, 64);
        sLabel.scale.set(10, 10, 10);
        sLabel.position.set(-100, 0, 0); 

        const eLabel = this.createTextSprite('E', 64, 64);
        eLabel.scale.set(10, 10, 10);
        eLabel.position.set(0, 0, 100);
    
        const wLabel = this.createTextSprite('W', 64, 64);
        wLabel.scale.set(10, 10, 10);
        wLabel.position.set(0, 0, -100);
        // Add labels to scene
        this.scene.add(nLabel);
        this.scene.add(sLabel);
        this.scene.add(eLabel);
        this.scene.add(wLabel);
    }    

    addGround() {
        // Create circular ground plane
        const groundGeometry = new THREE.CircleGeometry(100, 64); // Radius 100, 64 segments for smoothness
        const groundMaterial = new THREE.MeshBasicMaterial({
            color: 0x333333, // Dark gray for ground
            side: THREE.DoubleSide, // Visible from both sides
            transparent: true,
            opacity: 0.9 // Slightly transparent to see stars below
        });
        const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    
        // Position ground below starfield (y = -100)
        ground.position.set(0, 0, 0);
        ground.rotation.x = -Math.PI / 2; // Rotate to lie flat (perpendicular to y-axis)
    
        // Add to scene
        this.scene.add(ground);
    }

    addMusic(){
        // Create an AudioListener and attach it to the camera
        const listener = new THREE.AudioListener();
        this.camera.add(listener);

        // Create an Audio object and attach it to the listener
        this.sound = new THREE.Audio(listener);
        var sound = this.sound;
        // Load an audio file (for example, an MP3 file)
        const audioLoader = new THREE.AudioLoader();
        audioLoader.load('Vbazi.mp3', function(buffer) {
            sound.setBuffer(buffer);
            sound.setLoop(true);  // Set loop if needed
            sound.setVolume(0.5); // Set the initial volume
        });

        // Wait for a user gesture before playing
        const startMusic = () => {
            if (this.sound && !this.sound.isPlaying) {
                this.sound.play();
                console.log('Music started.');
            }
            // Remove listener after starting
            document.body.removeEventListener('click', startMusic);
        };

        document.body.addEventListener('click', startMusic);
    }
}