import * as THREE from 'three';
import {OrbitControls} from '/static/three/OrbitControls.js';
import {calculateLST, HoursMinutesSeconds, Degrees, parseRA, parseDec, positionFromRADEC, positionFromRADECrad } from './astroutils.js';
import {Controllers} from '/static/controllers.js';
import {Starfield} from '/static/starfield.js';

export class TelescopeSim {
    constructor(canvas, longitude = 14.5058, latitude = 46.0569) {
        this.canvas = canvas;
        this.actualLatitude = latitude * Math.PI / 180;     // Our initial actual latitude
        this.latitude = latitude * Math.PI / 180;           // Rotates interactively
		this.longitude = longitude;     // Keep in degrees
        this.currentLST = calculateLST(this.longitude);
        this.westPier = false;          // True if telescope is on the west side of the pier
		this.telescopeScale = 0.3;      // Scale factor for telescope size
        
        this.raAngle = 0;               // where the telescope is pointing, degrees 0 - 360
        this.decAngle = 0;              // where the telescope is pointing, degrees -90 - +90
        this.blockPointing = false;     // when simulating telescope pointing; block further pointing
        
        this.raAngleTarget = 0;         // telescope target angle, changes during animation
        this.decAngleTarget = 0;        // telescope target angle, changes during animation
        this.onSelectCallback = null;
        this.onActionCallback = null;

        this.tempMatrix = new THREE.Matrix4();

        this.controllers = null;

        this.addRotation = 0;

        this.initCatalogs();

        this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: false });
        //this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio); // Optimize for Quest 3
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        this.clock = new THREE.Clock();

        this.addSceneAndLighting(canvas);

        this.addGround(); 
        this.addSkyPoles();
        this.addTelescope();

        this.moveSound = null;
        this.ropeSound = null;
        this.ratchetSound = null;
        this.clickSound = null;
        this.listener = new THREE.AudioListener();
        this.camera.add(this.listener);

        this.addOrbitControls();

        this.starCatalog = [];
        this.starfield = new Starfield(this.starfieldGroup);

        this.addClickDetection();
        //this.addMusic();
        //this.addCoordinateAxes(this.scene);


        // Initial angles
        this.setAngles(this.raAngle, this.decAngle);

        this.resetPosition();

        // Start animation
        this.renderer.setAnimationLoop(() => this.animate()); 
    }    

    initCatalogs() {
        this.starCatalog = [];              // catalog of stars to display on sphere
        this.imageCatalog = [];             // catalog of images to display on sphere
        this.imageCatalog.push([null, null, "Live", null, null]);
        this.currentObjectCatalog = null;
        this.currentObjectIndex = null;
        this.currentObject = null;
    }
    
    addStarfield(starCatalog, minMagnitude = 5) {
        this.starCatalog = this.starfield.addStarCatalog(starCatalog, minMagnitude);
    }

    onSelect(funct) {
        this.onSelectCallback = funct;
    }
    onAction(funct) {
        this.onActionCallback = funct;
    }
    onFrame(funct) {
        this.onFrameCallback = funct;
    }

    addOrbitControls() {
        // OrbitControls
        this.controls = new OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 1;
        this.controls.maxDistance = 50;
        this.controls.enablePan = true;        
    }
    
    adaptDec(dec) {
        // adapt dec according to pier position and normalize to -180 ... +180
		if(this.westPier) {
            dec = 180 - dec;
        }
        while (dec > 180) dec -= 360;
        while (dec < -180) dec += 360;
        return dec;
    }
    adaptRa(ra) {
        // adapt dec according to pier position and normalize to -180 ... +180
		if(this.westPier) {
            ra = (ra + 180) % 360;
        }
        return ra;
    }

    animateToAngles(ra, dec) {
        this.raAngleTarget = this.adaptRa(ra);
        this.decAngleTarget = this.adaptDec(dec);
    
    }

    setAngles(ra, dec) {
        this.raAngle = this.adaptRa(ra);
        this.decAngle = this.adaptDec(dec);
        this.raAngleTarget = this.adaptRa(ra);
        this.decAngleTarget = this.adaptDec(dec);
    }

    meridianFlip() {
        this.raAngleTarget = (this.raAngle + 180) % 360;
        const decRot = Math.sign(this.decAngle) * (180 - 2 * Math.abs(this.decAngle));
        this.decAngleTarget += decRot;
        this.westPier = !this.westPier;
    }
    
    setPier(west = false) {
        this.westPier = west;
    }
     
    pointTelescope(raStr, decStr, animate=false) {
        
        if(this.blockPointing) return;

        const raHours = parseRA(raStr);
        const decDegrees = parseDec(decStr);        
        let raDiff = (raHours - this.currentLST) * 15 + 180;
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
        this.currentLST = calculateLST(this.longitude);
        this.starfieldGroup.rotation.y = - this.currentLST / 12 * Math.PI - this.addRotation;
        this.starfieldPolarGroup.rotation.z = -(Math.PI / 2 - this.latitude);
        this.polarGroup.rotation.z = -(Math.PI / 2 - this.latitude);

        const elapsedTime = this.clock.getElapsedTime();
        if(this.starMaterial) {
            this.starMaterial.uniforms.uTime.value = elapsedTime;
        }

        const delta = 0.2;
        var animating = false;
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
            animating = true;
        }
        if(this.decAngle !== this.decAngleTarget) {
            this.decAngle += Math.sign((this.decAngleTarget-this.decAngle)) * delta;
            if (Math.abs(this.decAngle - this.decAngleTarget) < 2*delta) {
                this.decAngle = this.decAngleTarget;
            }
            animating = true;
        }
        if(animating && this.moveSound && !this.moveSound.isPlaying) this.moveSound.play();
        if(!animating && this.moveSound && this.moveSound.isPlaying) this.moveSound.stop();

        this.raGroup.rotation.y = this.raAngle * Math.PI / 180 - this.addRotation;
        this.decGroup.rotation.z = this.decAngle * Math.PI / 180;

        this.updateLiveImagePos(elapsedTime);
        this.handleControllers(elapsedTime);

        if (this.renderer.xr.isPresenting) {
            this.renderer.render(this.scene, this.camera);
        } else {
            if(this.controls) this.controls.update();
            this.renderer.render(this.scene, this.camera);
        }

        if(this.onFrameCallback) this.onFrameCallback();
    }

    // Movement controls

    resetPosition() {
        if(this.userRig) {
            this.userRig.position.set(0,0,0);
        } else {
            this.camera.position.set(5,1.6,0);
            this.controls.target.set(0,2,0);
            this.controls.update(); 
        }
    }
    moveTo(dest, target = null) {
        const [x,y,z] = dest;
        if(this.userRig) {
            this.userRig.position.set(x,y,z);
        } else {
            this.camera.position.set(x,y,z);
            if(target) {
                const [tx,ty,tz] = dest;
                this.controls.target.set(tx,ty,tz);
            }
            this.controls.update(); 
        }
    }

    addClickDetection() {
        // Initialize raycaster
        this.raycaster = new THREE.Raycaster();
        this.raycaster.params.Points.threshold = 1; // Adjust for starfield point sensitivity
    
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
        const onRClick = (event) => {
            this.scaleImages(1.4);
        };
        
        const onDblClick = (event) => {
            mouse.x = (event.clientX / this.canvas.clientWidth) * 2 - 1;
            mouse.y = -(event.clientY / this.canvas.clientHeight) * 2 + 1;
            this.raycaster.setFromCamera(mouse, this.camera);
            this.handleRaycast();
            this.camera.updateProjectionMatrix();
            if(this.currentObjectIndex == null) {
                this.resetPosition();
                return;
            } 
            const [raStr, decStr] = this.currentObjectCatalog[this.currentObjectIndex];
            const [x, y, z] =  positionFromRADEC(raStr, decStr, this.starfieldGroup, 95, true);
            this.camera.position.set(x, y, z);
            const [x1, y1, z1] =  positionFromRADEC(raStr, decStr, this.starfieldGroup, 100, true);
            this.controls.target.set(x1, y1, z1);
            this.controls.update(); 
            this.removeCurrentLabel();
            this.currentObjectIndex = null;
            this.currentObjectCatalog = null;
    };
    

        // Add mouse event listener for non-VR
        this.canvas.addEventListener('click', onClick, false);
        this.canvas.addEventListener('dblclick', onDblClick, false);
        this.canvas.addEventListener('rclick', onRClick, false);
        
    
    }

    addControllers() {
        this.lastThumbPressTime = 0;
        this.controllers = new Controllers(this.renderer, this.userRig, this.scene);
        // Prepare controller slots
        // VR controller handler
        
        const onRSelect = () => {
            const controller = this.controllers.Right;
            // Make sure matrices are updated
            controller.updateMatrixWorld(true);
            // Get world position
            const position = new THREE.Vector3();
            controller.getWorldPosition(position);
            this.raycaster.set(position, controller.getWorldDirection(new THREE.Vector3()).negate());
            this.raycaster.camera = this.renderer.xr.getCamera(this.camera);
            this.handleRaycast();
            if(this.currentObject!=null) {
                this.clickSound.play();
            } else {
                this.imageCatalog.forEach(obj => {
                    if (obj[4] != null) {
                        obj[4].material.uniforms.showBorder.value = true;
                    }
                });    
            }
        };

        const onRSqueeze = () => {
            if(this.currentObject!=null) {
                this.controllers.hapticFeedback('right');
            } else {
                this.resetImageUniforms();
            }
        };

        const onRSqueezeEnd = () => {
            this.controllers.attachLaser(this.controllers.Right);
        };

        const onLSqueeze = () => {
            if(this.currentObject!=null) {
                this.controllers.hapticFeedback('left');
                if(this.ropeSound && !this.ropeSound.isPlaying) this.ropeSound.play();
            } else {
                this.resetImageUniforms();
            }
        };

        const onLSqueezeEnd = () => {
            this.controllers.attachLaser(this.controllers.Left);
            if(this.ropeSound && this.ropeSound.isPlaying) this.ropeSound.stop();
        };

        this.controllers.onRConnected((controller) => {
            controller.addEventListener('select', onRSelect);
            controller.addEventListener('squeezestart', onRSqueeze);
            controller.addEventListener('squeezeend', onRSqueezeEnd);
        });

        this.controllers.onLConnected((controller) => {
            controller.addEventListener('squeezestart', onLSqueeze);
            controller.addEventListener('squeezeend', onLSqueezeEnd);
        });

        this.controllers.attachEvent("right", 4, "start", () => {
                if(this.currentObjectIndex == null) return;
                const [raStr, decStr] = this.currentObjectCatalog[this.currentObjectIndex];
                this.pointTelescope(raStr, decStr, true);
                this.blockPointing = true;
        },1);        
        this.controllers.attachEvent("right", 4, "end", () => {
            this.blockPointing = false;
        },1);        

        this.controllers.attachEvent("right", 5, "start", () => {
                if(this.currentObjectIndex == null) return;
                if(this.onActionCallback) {
                    this.onActionCallback(this.currentObjectCatalog, this.currentObjectIndex);
                };
         },1);
    
        this.controllers.attachEvent("right", 3, "press", () => {
                this.latitude = this.actualLatitude; 
                this.addRotation = 0;
        },1);

        this.controllers.attachEvent("left", 3, "press", () => {
            this.scaleImages(); // reset scale
            // highlight all
            this.imageCatalog.forEach(obj => {
                if (obj[4] != null) {
                    obj[4].material.uniforms.showBorder.value = true;
                }
            });
        },1);

        // Oculus X button
        this.controllers.attachEvent("left", 4, "start", () => {
            if(this.currentObjectIndex == null) {
                this.resetPosition();
                return;
            }
            const [raStr, decStr] = this.currentObjectCatalog[this.currentObjectIndex];
            const [x, y, z] =  positionFromRADEC(raStr, decStr, this.starfieldGroup, 95, true);
            this.removeCurrentLabel();
            this.currentObjectIndex = null;
            this.userRig.position.set(x, y, z);    
        },1);

        this.controllers.attachEvent("left", 5, "start", () => {
        },1);
        this.controllers.attachEvent("left", 5, "end", () => {
        },1);

    }

    handleControllers(elapsedTime) {
        // Thumbstick axes
        if(!this.controllers) return;
        this.controllers.handleControllers(elapsedTime);

        const [x,y] = this.controllers.RthumbAxes();
        if (Math.abs(x) > 0.1 || Math.abs(y) > 0.1) {
            this.addRotation += x * 0.02; 
            if(Math.abs(y)>0.5) {
                this.latitude += y * 0.02; 
            }
        }       
        const [u,v] = this.controllers.LthumbAxes();
        if (Math.abs(u) > 0.1 || Math.abs(v) > 0.1) {
            if(Math.abs(v)>0.5) {
                const factor = v > 0 ? 1.01 : 1/1.01;
                if(this.currentObjectIndex!=null && this.currentObjectCatalog == this.imageCatalog) {
                    this.resizeMesh(this.imageCatalog[this.currentObjectIndex][4], factor);
                } else {
                    this.scaleImages(factor);
                }
            }
            if(Math.abs(u)>0.5) {
                if(this.currentObjectIndex!=null && this.currentObjectCatalog == this.imageCatalog) {
                    if(elapsedTime - this.lastThumbPressTime > 0.5) {
                        this.resetImageUniforms();
                        this.currentObjectIndex+=Math.sign(x);
                        if(this.currentObjectIndex>=this.currentObjectCatalog.length) this.currentObjectIndex = 1;
                        if(this.currentObjectIndex<1) this.currentObjectIndex = this.currentObjectCatalog.length-1;
                        this.highlightImage(this.currentObjectIndex);
                        this.lastThumbPressTime = elapsedTime;
                    }
                }
            }
        }
        const isFlying = this.controllers.LeftGamepad && this.controllers.LeftGamepad.buttons[1].pressed;
        if(this.currentObject!=null && isFlying) {           
            
            this.currentObject.updateMatrixWorld(true);
            const worldDir = new THREE.Vector3(0, 0, 1); // SphereGeometry faces +Z
            worldDir.applyQuaternion(this.currentObject.getWorldQuaternion(new THREE.Quaternion()));
            // Compute world position at radius r = 100
            const objectPos = worldDir.multiplyScalar(100);
            this.controllers.pointLaser('left', objectPos, this.controllers.Left.userData.color);

            const direction = objectPos.clone().sub(this.controllers.currentPositionL);
            let distance = direction.length();
            direction.normalize();

            // project controller velocity onto direction
            let velocityAlongDirection = -this.controllers.velocityL.clone().dot(direction) / 20;

            if (Math.abs(velocityAlongDirection) > 0.001) {
               // velocityAlongDirection = Math.max(-0.1 , Math.min(velocityAlongDirection, 0.1));
               distance = Math.max(-50,Math.min(50, distance));
               this.userRig.position.add(direction.multiplyScalar(velocityAlongDirection*distance));
            }
        }
        if(!isFlying && this.userRig.position.length() > 1) {
            // pulled towards origin
            const direction = this.controllers.currentPositionL.clone();
            const distance = direction.length();
            direction.normalize();
            this.userRig.position.add(direction.multiplyScalar(-0.1));
        }

        const isPulling = this.controllers.RightGamepad && this.controllers.RightGamepad.buttons[1].pressed;
        if(this.currentObject!=null && isPulling) {
            // Calculate velocity (pulling motion)
            // Check for pulling gesture (backward motion along controller's Z-axis)
            // Orient laser during pulling
            // Compute world direction from image mesh
            const worldDir = new THREE.Vector3(0, 0, 1); // SphereGeometry faces +Z
            worldDir.applyQuaternion(this.currentObject.getWorldQuaternion(new THREE.Quaternion()));
            this.currentObject.updateMatrixWorld(true);
            // Compute world position at radius r = 100
            const objectPos = worldDir.multiplyScalar(100);
            this.controllers.pointLaser('right', objectPos);

            const direction = objectPos.clone().sub(this.controllers.currentPositionR).normalize();

            // project controller velocity onto direction
            const velocityAlongDirection = -this.controllers.velocityR.clone().dot(direction) / 20;
            console.log("CP L:",this.controllers.currentPositionL);
            console.log("VAD R:",velocityAlongDirection);

            if (Math.abs(velocityAlongDirection) > 0.001) {
                const factor = (velocityAlongDirection > 0 ? 1+velocityAlongDirection : 1/(1+Math.abs(velocityAlongDirection)));
                this.resizeMesh(this.currentObject, factor);
                if(!this.clickSound.isPlaying) this.clickSound.play();

                // Move star toward user
                //const userPosition = this.userRig.position;
                //const direction = userPosition.clone().sub(this.currentObject.position).normalize();
                //const speed = 0.1; // Adjust speed
                //this.currentObject.position.add(direction.multiplyScalar(speed));
            }
        }
    }

    // Shared raycast logic
    handleRaycast() {
        const intersects = this.raycaster.intersectObjects([this.starfieldGroup], true);
        this.resetImageUniforms();
        if (intersects.length > 0) {
            const intersect = intersects[0];
            const point = intersect.point;
            var labelText = null;
            if(intersect.object.isPoints) {
                this.currentObjectIndex = intersect.index;
                this.currentObjectCatalog = this.starCatalog;
                this.currentObject = null;
                const [raStr, decStr, mag, name, constellation, HDnr] = this.starCatalog[this.currentObjectIndex];
                labelText = `${name} ${constellation} HD${HDnr} ${mag}`;
                console.log(`Selected star: RA=${raStr}, Dec=${decStr}, Label=${labelText}, Position=${point.x},${point.y},${point.z}`);
            } else {
                this.currentObjectIndex = intersect.object.userData.index;
                this.currentObjectCatalog = this.imageCatalog;
                this.currentObject = intersect.object;
                this.highlightImage(this.currentObjectIndex);
                const [raStr, decStr, name, texture, m] = this.imageCatalog[this.currentObjectIndex];
                labelText = name;
                labelText = null;
                console.log(`Selected image object: RA=${raStr}, Dec=${decStr}, name=${name}, Position=${point.x},${point.y},${point.z}`);
            }
            this.removeCurrentLabel();
            if(labelText) this.addCurrentLabel(point, labelText);
            if(this.onSelectCallback) this.onSelectCallback(this.currentObjectCatalog, this.currentObjectIndex);            
        } else {
            this.removeCurrentLabel();
            this.currentObjectIndex = null;
            this.currentObjectCatalog = null;
            this.currentObject = null;
            if(this.onSelectCallback) this.onSelectCallback(null, null);
            console.log('No star selected');
        }
    }

    base64ToBlob(base64, mime = 'image/jpeg') {
        const binary = atob(base64);
        const len = binary.length;
        const buffer = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
            buffer[i] = binary.charCodeAt(i);
        }
        return new Blob([buffer], { type: mime });
    }

    async addLiveImage(imageb64, arcsecondsPerPixel, rotation = 0) {
        const blob = this.base64ToBlob(imageb64);
        const url = URL.createObjectURL(blob);
        const dec = Degrees(this.decAngle);
        const ra = HoursMinutesSeconds(this.raAngle/15); 
        await this.addImage(url, "Live Image", ra, dec, arcsecondsPerPixel, rotation, 0);
        URL.revokeObjectURL(url); // Free memory
    }
    
    async updateLiveImage(imageb64) {
        const blob = this.base64ToBlob(imageb64);
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => {            
            this.imageCatalog[0][3].image = img;
            this.imageCatalog[0][3].needsUpdate = true;
            URL.revokeObjectURL(url); // Free memory
        };
        img.src = url;
    }

    updateLiveImagePos(){
        if(this.imageCatalog[0][3] != null) {            
            const raHours = (this.raAngle-180)/15 + this.currentLST;
            var raDeg = (((raHours * 15) % 360) + 360) % 360;
            this.imageCatalog[0][0] = HoursMinutesSeconds(raHours);
            this.imageCatalog[0][1] = Degrees(this.decAngle);
            const [x, y, z] = positionFromRADECrad(raDeg* Math.PI / 180, this.decAngle* Math.PI / 180, this.starfieldGroup, 100, true);
            const target = new THREE.Vector3(x, y, z);
            this.imageCatalog[0][4].lookAt(target);    
        }
    }


    resetImageUniforms() {
        for(var i=0; i< this.imageCatalog.length; i++) {
            const mesh = this.imageCatalog[i][4];
            if( mesh != null) {
                mesh.material.uniforms.gamma.value = 1;
                mesh.material.uniforms.transparency.value = 0.5;
                mesh.material.uniforms.brightness.value = 1;
                mesh.material.uniforms.showBorder.value = false;
            }
        }
    }
    highlightImage(index) {
        if(index != null && index >=0 && index < this.imageCatalog.length) {
            const mesh = this.imageCatalog[index][4];
            if( mesh != null) {
                mesh.material.uniforms.gamma.value = 1.2;
                mesh.material.uniforms.transparency.value = 1;
                mesh.material.uniforms.brightness.value = 1;
                mesh.material.uniforms.showBorder.value = true;
            }
        }
    }

    scaleImages(factor = null) {
        for(var i=0; i< this.imageCatalog.length; i++) {
            const mesh = this.imageCatalog[i][4];
            if(mesh != null) {
                this.resizeMesh(mesh, factor);
            }
        }
    }
    
    resizeMesh(mesh, factor) {
        const oldGeom = mesh.geometry;
    
        // Extract old parameters
        const r = oldGeom.parameters.radius;

        const widthRad = Math.min(2*Math.PI, factor ? oldGeom.parameters.phiLength * factor : mesh.userData.originalSize.widthRad);
        const heightRad = Math.min(Math.PI, factor ? oldGeom.parameters.thetaLength * factor : mesh.userData.originalSize.heightRad);
    
        const newGeom = new THREE.SphereGeometry(
            r, 
            oldGeom.parameters.widthSegments, 
            oldGeom.parameters.heightSegments,
            oldGeom.parameters.phiStart - (widthRad - oldGeom.parameters.phiLength)/2,
            widthRad,
            oldGeom.parameters.thetaStart - (heightRad - oldGeom.parameters.thetaLength)/2,
            heightRad
        );
        
        mesh.geometry.dispose(); // Free GPU memory
        mesh.geometry = newGeom;
    }

    async addImage(img, name, ra, dec, arcsecondsPerPixel, rotation = 0, index = null) {
        
        if (name === "Luna") {
            ra = HoursMinutesSeconds(this.currentLST);
        }
        if (name === "Saturn" ) {
            ra = HoursMinutesSeconds(this.currentLST+1);
        }
    
        const catalogIndex = (index == null ? this.imageCatalog.length : index);
        if(index == null) this.imageCatalog.push(null);

        const loader = new THREE.TextureLoader();
        const texture = await new Promise((resolve, reject) => {
            loader.load(
                img,
                tex => {
                    tex.flipY = false; // ← IMPORTANT
                    resolve(tex);
                },
                undefined, // On progress (not needed)
                reject     // On error, reject the promise
            );
        });

        const mesh = this.addImageTexture(texture, ra, dec, arcsecondsPerPixel, rotation, catalogIndex);        
        this.imageCatalog[catalogIndex] = [ra, dec, name, texture, mesh ];
        return catalogIndex;
    }

    addImageTexture(texture, ra, dec, arcsecondsPerPixel, rotation, catalogIndex){
        // Now that texture is loaded, we know its size
        const imageWidth = texture.image.width;
        const imageHeight = texture.image.height;
        const r = 100;

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
        const material = this.makeImageMaterial(texture);
        material.uniforms.transparency.value = 0.8;
        //material.uniforms.mirror.value = true;

        // Create mesh
        const segmentMesh = new THREE.Mesh(sphereSegment, material);
        segmentMesh.userData.index = catalogIndex;
        segmentMesh.userData.originalSize = {
            widthRad,
            heightRad
        };

        // Position
        const [x, y, z] = positionFromRADEC(ra, dec, this.starfieldGroup);
        //segmentMesh.position.set(x, y, z);
        segmentMesh.position.set(0, 0, 0);

        // Rotate toward RA/Dec
        const target = new THREE.Vector3(x, y, z);
        segmentMesh.lookAt(target);

        // Adjust if needed
        segmentMesh.rotateZ(Math.PI-rotation);
        
        this.starfieldGroup.add(segmentMesh);

        return segmentMesh;
    }
    makeImageMaterial(texture) {
        return new THREE.ShaderMaterial({
            uniforms: {
                map: { value: texture },
                brightness: { value: 1.0 },
                gamma: { value: 1.0 },
                transparency: { value: 1.0 },
                mirror: { value: false },
                showBorder: { value: false },
                borderColor: { value: new THREE.Color(1, 0, 0) }, // Red
                borderWidth: { value: 0.03 }, // In UV space (0 to 1)
            },
            vertexShader: `
                varying vec2 vUv;
                void main() {
                    vUv = uv;
                    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                uniform sampler2D map;
                uniform float brightness;
                uniform float gamma;
                uniform float transparency;
                uniform bool mirror;
                uniform bool showBorder;
                uniform vec3 borderColor;
                uniform float borderWidth;
                varying vec2 vUv;
                
                void main() {
                    vec2 uv = vUv;
                    if (mirror) uv.x = 1.0 - uv.x;
                    vec4 texColor = texture2D(map, uv);
                    texColor.rgb *= brightness;
                    texColor.rgb = pow(texColor.rgb, vec3(1.0 / gamma));
                    texColor.a *= transparency;
                    // Border effect
                    if (showBorder) {
                        float edgeDist = min(min(uv.x, 1.0 - uv.x), min(uv.y, 1.0 - uv.y));
                        float border = smoothstep(0.0, borderWidth, edgeDist); // 0 at edge, 1 inside
                        if (border < 1.0) {
                            // Inside border area: blend border color
                            texColor.rgb = mix(borderColor, texColor.rgb, border); // border → texColor
                        }
                    }
                    gl_FragColor = texColor;
                }
            `,
            transparent: true,
            side: THREE.DoubleSide
        });
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
    


    enableWebXR(canvas) {
        // Enable WebXR on renderer
        this.renderer.xr.enabled = true;
       
        this.camera = new THREE.PerspectiveCamera(70, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);

        this.userRig = new THREE.Group();
        this.userRig.add(this.camera);
        this.scene.add(this.userRig);
        
        // Adjust camera for VR
        this.camera.position.set(0, 0, 0);
        this.userRig.near = 0.1; // Adjust near plane for VR
        this.userRig.far = 1000; // Ensure far plane covers starfield
        this.resetPosition();        
        this.addControllers();
        
        this.camera.add(this.listener);

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


    addSceneAndLighting(canvas) {
        // Scene setup
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(30, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
        //this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
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

    }

    addTelescope() {

        // Materials
        this.bodyMaterial = new THREE.MeshPhongMaterial({ color: 0x2222aa, shininess: 50 });
        this.axisMaterial = new THREE.MeshPhongMaterial({ color: 0xff0000, shininess: 50 });
        const laserMaterial = new THREE.LineBasicMaterial({ color: 0x0000ff }); 
        this.shaftMaterial = new THREE.MeshPhongMaterial({ color: 0x555555, shininess: 50 });
        this.weightMaterial = new THREE.MeshPhongMaterial({ color: 0x333333, shininess: 50 });
        const textureLoader = new THREE.TextureLoader();
        const telescopeTexture = textureLoader.load('/static/img/PIPITREK_wash.webp');
        this.telescopeMaterial = new THREE.MeshPhongMaterial({
            map: telescopeTexture,
            shininess: 50,
            side: THREE.DoubleSide
        });
        this.telescopeBackMaterial = new THREE.MeshPhongMaterial({ color: 0x090909, shininess: 20 });


        // Dimensions
        const shaftHeight = 1.6;
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

    addSounds(directory) {
        this.moveSound = new THREE.PositionalAudio(this.listener);
        this.raGroup.add(this.moveSound);
        const audioLoader = new THREE.AudioLoader();
        audioLoader.load(directory+"/SimMove.ogg", (buffer) => {
            this.moveSound.setBuffer(buffer);
            this.moveSound.setRefDistance(10); // How quickly it fades with distance
            this.moveSound.setRolloffFactor(1.1);
            this.moveSound.setLoop(true);
            this.moveSound.setVolume(0.6);
        });

        this.clickSound = new THREE.PositionalAudio(this.listener);
        this.userRig.add(this.clickSound);
        audioLoader.load(directory+"/Click.ogg", (buffer) => {
            this.clickSound.setBuffer(buffer);
            this.clickSound.setLoop(false);
            this.clickSound.setVolume(0.8);
        });
        this.ratchetSound = new THREE.PositionalAudio(this.listener);
        this.userRig.add(this.ratchetSound);
        audioLoader.load(directory+"/Ratchet.ogg", (buffer) => {
            this.ratchetSound.setBuffer(buffer);
            this.ratchetSound.setLoop(false);
            this.ratchetSound.setVolume(0.8);
        });
        this.ropeSound = new THREE.PositionalAudio(this.listener);
        this.userRig.add(this.ropeSound);
        audioLoader.load(directory+"/Rope.ogg", (buffer) => {
            this.ropeSound.setBuffer(buffer);
            this.ropeSound.setLoop(false);
            this.ropeSound.setVolume(0.8);
        });

    }

    addMusic(song){
        // Create an Audio object and attach it to the listener
        this.sound = new THREE.Audio(this.listener);
        var sound = this.sound;
        // Load an audio file (for example, an MP3 file)
        const audioLoader = new THREE.AudioLoader();
        audioLoader.load(song, function(buffer) {
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