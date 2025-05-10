import * as THREE from 'three';
import {GLTFLoader} from './three/loaders/GLTFLoader.js';
import {FontLoader} from './three/loaders/FontLoader.js';
import {OrbitControls} from './three/OrbitControls.js';
import Stats from './three/stats.module.js';
import * as AstroUtils from './astroutils.js';
import * as TextUtils from './textutils.js';
import {Controllers} from './controllers.js';
import {Starfield} from './starfield.js';
import {Telescope} from './telescope.js';
import {TelescopeGUI} from './TelescopeGUI.js';
import {createObservingPlatform,addSkyPoles,addCoordinateAxes, addGround} from './objects.js';
import { getImageDSS,getImageDSSUrl } from './dssTools.js';

export class TelescopeSim {
    constructor(container, canvas, longitude = 14.5058, latitude = 46.0569) {
        this.container = container;
        this.canvas = canvas;
        this.currentLST = AstroUtils.calculateLST(this.longitude);
        this.onSelectCallback = null;
        this.onActionCallback = null;
        this.tempMatrix = new THREE.Matrix4();
        this.controllers = null;
        this.addRotation = 0;
        this.height = 1.6;
        this.latitude = latitude * Math.PI / 180,           // Rotates interactively
		this.longitude = longitude;     // Keep in degrees

        this.currentObjectCatalog = null;
        this.currentObjectIndex = null;
        this.currentObject = null;

        this.currentLabels = [];
        this.currentLabel = null;

        this.settings = {
            actualLatitude: latitude * Math.PI / 180,     // Our initial actual latitude
            showStars: true,
            showGalaxies: true,
            showNebulae: true,
            showClusters: true,
            showConstellations: true,
            showLabels: false,
            showTelescope: true,
            showTelescopeScreen: true,
            showGround: true,
            gravity: true
        }

        this.renderer = new THREE.WebGLRenderer({
             canvas: this.canvas,
             antialias: true,
             //logarithmicDepthBuffer: true,
             //alpha: true
        });

        this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        this.renderer.setPixelRatio(window.devicePixelRatio); // Optimize for Quest 3
        this.renderer.outputEncoding = THREE.sRGBEncoding;
        this.renderer.outputColorSpace = THREE.SRGBColorSpace;
        this.renderer.toneMapping = THREE.LinearToneMapping; // Try other options like LinearToneMapping
        this.renderer.toneMappingExposure = 1.0; // Try lowering if it's washed out
        this.renderer.setSize(window.innerWidth, window.innerHeight);
        
        this.clock = new THREE.Clock();

        this.addSceneAndLighting(canvas);

        this.ground = addGround(0, this.scene);
        addSkyPoles(this.scene);
        
        this.telescope = new Telescope(0.25, this.height);
        this.scene.add(this.telescope.group);

        this.moveSound = null;
        this.ropeSound = null;
        this.ratchetSound = null;
        this.clickSound = null;
        this.audioListener = new THREE.AudioListener();
        this.camera.add(this.audioListener);
        this.addOrbitControls();
        this.addControllers();
        //this.addStats();

        this.starfield = new Starfield(this.starfieldGroup);

        this.addClickDetection();
        //this.addMusic();
        //this.addCoordinateAxes(this.scene);
        //this.userRig.add(createObservingPlatform());

        this.resetPosition();

        // Start animation
        this.renderer.setAnimationLoop((time, frame) => this.animate(time, frame)); 

        const loader = new FontLoader();
        loader.load('/static/three/fonts/optimer_regular.typeface.json', (font) => {
            this.font = font;
        });

        TelescopeGUI.init(this.container, this.renderer, this.scene, this.camera, this.userRig);
        this.telescopeGUI = new TelescopeGUI(this.scene, this.userRig, this.settings, this.starfield, this, this.telescope);

        //this.scene.add(new THREE.CameraHelper(this.telescopeCamera));
        //this.scene.add(new THREE.CameraHelper(this.camera)); // main VR camera

    }    

    setVisibility() {
        this.telescope.group.visible = this.settings.showTelescope;
        this.telescope.screen.visible = this.settings.showTelescopeScreen;
        this.starfield.enableCatalogs('star',this.settings.showStars);
        this.starfield.enableCatalogs('galaxy',this.settings.showGalaxies);
        this.starfield.enableCatalogs('nebula',this.settings.showNebulae);
        this.starfield.enableCatalogs('cluster',this.settings.showClusters);
    }
    
    addStarfield(catalog, minMagnitude = 5) {
        this.starfield.addStarCatalog(catalog, minMagnitude);        
    }

    addNGCs(catalog, minMagnitude = 13) {
        this.starfield.addGalaxyCatalog(catalog, minMagnitude);
        this.starfield.addNebulaCatalog(catalog, minMagnitude);
        this.starfield.addClusterCatalog(catalog, minMagnitude);        
    }

    pointTelescope(raStr, decStr, animate=false) {
        this.telescope.pointTelescope(raStr, decStr, animate);
    }
    meridianFlip() {
        this.telescope.meridianFlip();
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
    

    resize(width, height) {
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate(time, frame) {
        // Update starfield rotation based on current LST
        this.currentLST = AstroUtils.calculateLST(this.longitude);
        this.telescope.setLST(this.currentLST);
        this.starfieldGroup.rotation.y = - this.currentLST / 12 * Math.PI - this.addRotation;
        // update polar angle
        this.starfieldPolarGroup.rotation.z = -(Math.PI / 2 - this.latitude);        
        this.telescope.setPolarAngle(-(Math.PI / 2 - this.latitude));

        // animate stars
        const elapsedTime = this.clock.getElapsedTime();

        // animate telescope
        this.telescope.animate(this.addRotation);
        
        // adapt stars to telescope camera position offset .. remove parralax ;)
        this.starfieldPolarGroup.position.copy(this.telescope.cameraPosition);
        
        this.starfield.animateStars(elapsedTime);
        this.starfield.updateLiveImagePos(elapsedTime);
        this.handleControllers(elapsedTime);


        if(this.controls) this.controls.update();
        
        this.scaleLabel(this.currentLabel);
        for(const label of this.currentLabels) {
            this.scaleLabel(label);
        }
        
        if(this.stats) {
            this.stats.update();
            this.statsTexture.needsUpdate = true; // Mark for update
        }

        if(this.telescopeGUI) this.telescopeGUI.update(frame);

        this.telescope.renderScreen(this.renderer, this.scene);
        
        this.renderer.render(this.scene, this.camera);

        if(this.onFrameCallback) this.onFrameCallback();
    }

    // Movement controls

    resetPosition() {
        this.userRig.rotation.set(0,0,0);
        this.moveTo([1,0,1]);
    }
    
    moveTo(dest, target = null) {
        const [x,y,z] = dest;
        this.userRig.position.set(x,y,z);
        if(target && this.controls) {
            const [tx,ty,tz] = dest;
            this.controls.target.set(tx,ty,tz);
            this.controls.update(); 
        }
    }
    moveRel(vec) {
        this.userRig.position.add(vec);
    }

    distanceTo(point) {
        const dx = this.userRig.position.x - (point ? point.x : 0);
        const dy = this.userRig.position.y - (point ? point.y : 0);
        const dz = this.userRig.position.z - (point ? point.z : 0);
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }
    getPosition() {
        return this.userRig.position.clone();
    }

    addClickDetection() {
        // Initialize raycaster
        this.raycaster = new THREE.Raycaster();
        this.raycaster.params.Points.threshold = 1; // Adjust for starfield point sensitivity
        this.raycaster.params.Line.threshold = 0.1; 
    
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
            this.starfield.scaleImages(1.4);
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
            const [x, y, z] =  AstroUtils.positionFromRADEC(raStr, decStr, this.starfieldGroup, 95, true);
            this.camera.position.set(x, y, z);
            const [x1, y1, z1] =  AstroUtils.positionFromRADEC(raStr, decStr, this.starfieldGroup, 100, true);
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
        this.lastSelectTime = 0;
        this.controllers = new Controllers(this.renderer, this.userRig, this.scene);
        
        // Prepare controller slots
        // VR controller handler

        const onRSqueeze = () => {
            if(this.currentObject!=null) {
                this.controllers.hapticFeedback('right');
            } else {
                this.starfield.resetImageUniforms();
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
                this.starfield.resetImageUniforms();
            }
        };

        const onLSqueezeEnd = () => {
            this.controllers.attachLaser(this.controllers.Left);
            if(this.ropeSound && this.ropeSound.isPlaying) this.ropeSound.stop();
        };

        this.controllers.onRConnected((controller) => {
            controller.addEventListener('squeezestart', onRSqueeze);
            controller.addEventListener('squeezeend', onRSqueezeEnd);
        });

        this.controllers.onLConnected((controller) => {
            controller.addEventListener('squeezestart', onLSqueeze);
            controller.addEventListener('squeezeend', onLSqueezeEnd);
        });

        this.controllers.attachEvent("right", 0, "start", () => {
            this.starfield.clearSphereIntersecion();
            this.lastSelectTime = this.clock.getElapsedTime();
            this.raycaster.setFromXRController(this.controllers.Right);
            this.raycaster.camera = this.camera;
            //this.telescopeGUI.handleControllerClick(this.raycaster);
            this.handleRaycast();
            if(this.currentObject!=null) {
                this.clickSound.play();
            } else {
                this.starfield.markImages();
            }
        },1);        
        
        this.controllers.attachEvent("right", 0, "end", () => {
            const selections = this.starfield.select();
            this.raycaster.setFromXRController(this.controllers.Right);
            const point = new THREE.Vector3();
            const hit = this.raycaster.ray.intersectSphere(this.starfield.sphere, point);
            this.lastSelectTime = 0;

            if (selections.length > 0) {
                var labelText = "";
                this.currentObject = null;
                this.removeCurrentLabel();
                for(const sel of selections) {
                    if(this.currentObject == null) {
                        this.currentObject = sel.object;
                        this.currentObjectIndex = sel.index;
                        this.currentObjectCatalog = sel.catalog;
                    }
                    this.starfield.getWorldPosition(sel.object, sel.index, point);
                    labelText = this.starfield.getLabelText(sel.object, sel.index);
                    const labelSprite = TextUtils.createTextSprite(labelText);
                    labelSprite.position.copy(point);
                    this.scene.add(labelSprite);
                    this.currentLabels.push(labelSprite);
                    this.scaleLabel(labelSprite);
                    //labelText += this.starfield.getLabelText(sel.object, sel.index) +"\n";
                }
                //if(labelText) this.addCurrentLabel(point, labelText);
            }
            if(this.currentObject == null) this.starfield.resetImageUniforms();

        },1);        


        this.controllers.attachEvent("right", 4, "start", () => {
                if(this.currentObjectIndex == null) return;
                const [raStr, decStr] = this.currentObjectCatalog[this.currentObjectIndex];
                const imageUrl = getImageDSSUrl(raStr, decStr, 50, 50);
                this.addImage(imageUrl, "new img", raStr, decStr, 0, 0, null, 50*60);
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
                this.latitude = this.settings.actualLatitude; 
                this.addRotation = 0;
        },1);


            
        this.controllers.attachEvent("left", 0, "press", () => {
            this.telescopeGUI.toggle();
        },1);

        this.controllers.attachEvent("left", 3, "press", () => {
            this.starfield.scaleImages(); // reset scale
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
            const [x, y, z] =  AstroUtils.positionFromRADEC(raStr, decStr, this.starfieldGroup, 95, true);
            this.removeCurrentLabel();
            this.currentObjectIndex = null;
            this.moveTo([x,y,z]);
        },1);

        this.controllers.attachEvent("left", 5, "start", () => {
            this.telescope.screenToEye(this.camera, this.renderer);
        },1);
        this.controllers.attachEvent("left", 5, "end", () => {
            this.telescope.screenToScreen(this.camera, this.renderer);
        },1);

        this.controllers.onMenuPressed(() => {
            this.telescopeGUI.toggle();
        });

    }

    handleControllers(elapsedTime) {

        // Thumbstick axes
        if(!this.controllers) return;
        this.controllers.handleControllers(elapsedTime);

        const [x,y] = this.controllers.RthumbAxes();
        if(this.currentObject == this.telescope.group) {
            // move the scope
            const delta = Math.PI/3600;
            if (Math.abs(x) > 0.1 || Math.abs(y) > 0.1) {
                this.telescope.move(x*delta*3, y*delta*3);
            }
        } else {
            // move the sky
            if (Math.abs(x) > 0.1 || Math.abs(y) > 0.1) {
                this.addRotation += x * 0.02; 
                if(Math.abs(y)>0.7) {
                    this.latitude += y * 0.01; 
                }
            }
        }

        const [u,v] = this.controllers.LthumbAxes();
        if(this.currentObject == this.telescope.group) {
            // scale images
            if(Math.abs(v)>0.2) {
                const factor = v > 0 ? 1.01 : 1/1.01;
                if(this.currentObjectIndex!=null && this.currentObjectCatalog == this.imageCatalog) {
                    this.starfield.scaleImages(factor, this.currentObjectIndex);
                } else {
                    this.starfield.scaleImages(factor);
                }
            }
            // scale telescope FOV
            if(Math.abs(u)>0.2) {
                if(elapsedTime - this.lastThumbPressTime > 0.1) {
                    this.lastThumbPressTime = elapsedTime;
                    const factor = u > 0 ? 1.01 : 1/1.01;
                    this.telescope.setFOV(this.telescope.getFOV()*factor);
                }
            }
        } else {
            // move user rig
            const delta = 0.1;
            if(Math.abs(v)>0.2) {
                this.userRig.position.x += v * delta;
            }
            if(Math.abs(u)>0.2) {
                this.userRig.position.z += u * delta;
            }
        }

        // face out
/*
        const center = new THREE.Vector3(0, 0, 0);
        const position = this.userRig.position.clone();
        const outward = position.clone().sub(center).normalize();

        // Step 1: Reset rotation
        this.userRig.rotation.set(0, 0, 0);

        // Step 2: Rotate around Y axis to face outward in XZ plane
        const flatDir = outward.clone();
        flatDir.y = 0;
        flatDir.normalize();
        const yaw = Math.atan2(flatDir.x, flatDir.z);
        this.userRig.rotateY(yaw);

        // Step 3: Tilt backward to align with full 3D direction
        const flatLength = Math.sqrt(outward.x ** 2 + outward.z ** 2);
        const pitch = Math.atan2(outward.y, flatLength);
        this.userRig.rotateX(-pitch);
*/


        const isSelecting = this.controllers.RightGamepad && this.controllers.RightGamepad.buttons[0].pressed;
        if(isSelecting) {
            if(this.lastSelectTime!=0 && (elapsedTime - this.lastSelectTime > 0.5)) {
                this.raycaster.setFromXRController(this.controllers.Right);
                this.starfield.addSphereIntersecion(this.raycaster.ray);   
            }
        }



        const isFlying = this.controllers.LeftGamepad && this.controllers.LeftGamepad.buttons[1].pressed;
        if(this.currentObject!=null && isFlying) {           
            
            const objectPos = this.getObjectPos( this.currentObject, this.currentObjectIndex);
            this.controllers.pointLaser('left', objectPos, this.controllers.Left.userData.color);

            const direction = objectPos.clone().sub(this.controllers.currentPositionL);
            let distance = direction.length();
            direction.normalize();

            // project controller velocity onto direction
            let velocityAlongDirection = -this.controllers.velocityL.clone().dot(direction) / 20;

            if (Math.abs(velocityAlongDirection) > 0.001) {
               distance = Math.max(-50,Math.min(50, distance));
               this.moveRel(direction.multiplyScalar(velocityAlongDirection*distance));
            }
        }
        if(!isFlying && this.settings.gravity) {
            // pulled towards origin
            if(this.distanceTo() > 3) {
                const direction = this.getPosition().normalize();
                this.moveRel(direction.multiplyScalar(-0.1));
            } else if(this.distanceTo() > 1) {
                this.resetPosition();
            }
        }


        const isPulling = this.controllers.RightGamepad && this.controllers.RightGamepad.buttons[1].pressed;
        if(this.currentObject!=null && isPulling && this.currentObject.name=='image') {
            // Calculate velocity (pulling motion)
            // Check for pulling gesture (backward motion along controller's Z-axis)
            // Orient laser during pulling
            const objectPos = this.getObjectPos( this.currentObject, this.currentObjectIndex);
            this.controllers.pointLaser('right', objectPos);
            const direction = objectPos.clone().sub(this.controllers.currentPositionR).normalize();

            // project controller velocity onto direction
            const velocityAlongDirection = -this.controllers.velocityR.clone().dot(direction) / 20;
            if (Math.abs(velocityAlongDirection) > 0.001) {
                const factor = (velocityAlongDirection > 0 ? 1+velocityAlongDirection : 1/(1+Math.abs(velocityAlongDirection)));
                this.starfield.scaleImages(factor, this.currentObjectIndex);
                if(!this.clickSound.isPlaying) this.clickSound.play();
            }
        }
    }

    getObjectPos(object, index) {
        const objectPos = new THREE.Vector3();
        if(object.name == 'catalog' || object.name == 'image') {
            this.starfield.getWorldPosition(object, index, objectPos);
        } else {
            object.getWorldPosition(objectPos);
        }
        return objectPos;
    }

    // Shared raycast logic
    handleRaycast() {
        
        this.starfield.resetImageUniforms();
        this.telescope.select(false);
        this.currentObject = null;       
        let labelText = null;
        let point = null;

        // try telescope
        const it = this.raycaster.intersectObjects([this.telescope.group], true);
        if (it.length > 0) {
            this.currentObject = this.telescope.group;
            this.currentObjectIndex = null;
            this.currentObjectCatalog = null;
            this.telescope.select(true);
            return;
        }

        // check for image hits
        const intersects = this.raycaster.intersectObjects([this.starfieldGroup], true);
        if (intersects.length > 0) {
            for(const intersect of intersects) {
                point = intersect.point;
                if(intersect.object.name=='image') {
                    this.currentObject = intersect.object;
                    this.currentObjectIndex = intersect.object.userData.index;
                    this.currentObjectCatalog = this.starfield.imageCatalog;
                    this.starfield.highlightImages(this.currentObjectIndex);
                    break;
                } else if(intersect.object.name=='catalog') {
                    this.currentObject = intersect.object;
                    this.currentObjectIndex = intersect.instanceId;
                    this.currentObjectCatalog = this.starfield.getCatalog(intersect.object);
                    break;                
                }
            }
        }

        // check for catalog hits using sphere intersects
        if(this.currentObject == null) {
            const pointV = new THREE.Vector3();
            this.raycaster.ray.intersectSphere(this.starfield.sphere, pointV);
            const selected = this.starfield.selectAt(this.raycaster.ray);
            for(const sel of selected) {
                this.currentObject = sel.object;
                this.currentObjectIndex = sel.index;
                this.currentObjectCatalog = sel.catalog;
                point = pointV;
                break;
            }
        }
        if(this.currentObject != null) {
            labelText = this.starfield.getLabelText(this.currentObject, this.currentObjectIndex);
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

    addLiveImage(imageb64, arcsecondsPerPixel, rotation = 0) {
        return this.starfield.addLiveImage(imageb64, arcsecondsPerPixel, rotation);
    }

    updateLiveImage(imageb64) {
        return this.starfield.updateLiveImage(imageb64);
    }

    addImage(img, name, ra, dec, arcsecondsPerPixel, rotation = 0, index = null, widthArcsec = null) {
        
        if (name === "Luna") {
            ra = AstroUtils.HoursMinutesSeconds(this.currentLST);
        }
        if (name === "Saturn" ) {
            ra = AstroUtils.HoursMinutesSeconds(this.currentLST+1);
        }
    
        return this.starfield.addImage(img, name, ra, dec, arcsecondsPerPixel, rotation, index, widthArcsec);
    }


    scaleLabel(label) {
        const scalefactor = 0.0005; // Adjust this value to control the scaling factor
        if(label) {
            const distance = label.position.distanceTo(this.getPosition());
            label.scale.set(
                label.userData.width*distance*scalefactor,
                label.userData.height*distance*scalefactor,
                1
            ); 
        }
    }

    removeCurrentLabel() {
        if(this.currentLabels) {
            this.currentLabels.forEach(label => {   
                this.scene.remove(label);
                label.geometry.dispose(); // Free GPU memory
                label.material.dispose(); // Free GPU memory
            });
            this.currentLabels = [];
        }         
        
        if (this.currentLabel) {
            this.scene.remove(this.currentLabel);
            this.currentLabel.geometry.dispose(); // Free GPU memory
            this.currentLabel.material.dispose(); // Free GPU memory
            this.currentLabel = null;
        }
    }

    addCurrentLabel2(point, labelText) {
         // Create and position new label
        const labelSprite = TextUtils.createTextSprite2(labelText);
        labelSprite.scale.set(0.04, 0.04, 0.04);
        labelSprite.position.copy(point);
        labelSprite.position.x += 0.5; // Offset for visibility
        this.scene.add(labelSprite);
        this.currentLabel = labelSprite;
    }
    
    addCurrentLabel(point, labelText) {
         // Create and position new label
        if(this.currentLabel) this.removeCurrentLabel();
         const labelSprite = TextUtils.createTextSprite(labelText);
        labelSprite.position.copy(point);
        this.scene.add(labelSprite);
        this.currentLabel = labelSprite;
        this.scaleLabel(labelSprite);
    }


    enableWebXR() {
        // Enable WebXR on renderer
        this.renderer.xr.enabled = true;
        
        // Adjust camera for VR
        this.camera.position.set(0, 0, 0);
        this.resetPosition();        
        this.camera.add(this.audioListener);

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
        this.camera = new THREE.PerspectiveCamera(30, canvas.clientWidth / canvas.clientHeight, 0.1, 500);
        //this.camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        // Lighting
        this.ambientLight = new THREE.AmbientLight(0x404040, 0.4);
        this.scene.add(this.ambientLight);
        
        this.directionalLight = new THREE.DirectionalLight(0xffffff, 0.4);
        this.directionalLight.position.set(-5, 5, 0);
        this.scene.add(this.directionalLight);

        this.directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
        this.directionalLight2.position.set(1, 10, 0);
        this.scene.add(this.directionalLight2);

        // Groups
        this.starfieldGroup = new THREE.Group();
        this.starfieldPolarGroup = new THREE.Group();
        this.scene.add(this.starfieldPolarGroup);
        this.starfieldPolarGroup.add(this.starfieldGroup);


        // User rig
        this.userRig = new THREE.Group();
        this.userRig.near = 0.1; // Adjust near plane for VR
        this.userRig.far = 1000; // Ensure far plane covers starfield
        this.userRig.add(this.camera);
        this.scene.add(this.userRig);
        this.camera.position.set(5,1.6,0);  // non-VR
        
    }
    addSounds(directory) {
        this.moveSound = new THREE.PositionalAudio(this.audioListener);
        this.telescope.group.add(this.moveSound);
        this.telescope.moveSound = this.moveSound;
        const audioLoader = new THREE.AudioLoader();
        audioLoader.load(directory+"/DomeMove.ogg", (buffer) => {
            this.moveSound.setBuffer(buffer);
            this.moveSound.setRefDistance(10); // How quickly it fades with distance
            this.moveSound.setRolloffFactor(1.1);
            this.moveSound.setLoop(true);
            this.moveSound.setVolume(0.6);
        });


        this.clickSound = new THREE.PositionalAudio(this.audioListener);
        this.camera.add(this.clickSound);
        audioLoader.load(directory+"/Click.ogg", (buffer) => {
            this.clickSound.setBuffer(buffer);
            this.clickSound.setLoop(false);
            this.clickSound.setVolume(0.8);
        });
        this.ratchetSound = new THREE.PositionalAudio(this.audioListener);
        this.camera.add(this.ratchetSound);
        audioLoader.load(directory+"/Ratchet.ogg", (buffer) => {
            this.ratchetSound.setBuffer(buffer);
            this.ratchetSound.setLoop(false);
            this.ratchetSound.setVolume(0.8);
        });
        this.ropeSound = new THREE.PositionalAudio(this.audioListener);
        this.camera.add(this.ropeSound);
        audioLoader.load(directory+"/Rope.ogg", (buffer) => {
            this.ropeSound.setBuffer(buffer);
            this.ropeSound.setLoop(false);
            this.ropeSound.setVolume(0.8);
        });

    }

    addMusic(song){
        // Create an Audio object and attach it to the audioListener
        this.sound = new THREE.Audio(this.audioListener);
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
            // Remove event listener after starting
            document.body.removeEventListener('click', startMusic);
        };

        document.body.addEventListener('click', startMusic);
    }


    addStats() {
        this.stats = new Stats();
        document.body.appendChild(this.stats.dom); // Normal 2D mode
        // For XR, render it into a texture
        const canvas = this.stats.dom.querySelector('canvas');
        this.statsTexture = new THREE.CanvasTexture(canvas);
        const material = new THREE.SpriteMaterial({ map: this.statsTexture, transparent: true });
        const sprite = new THREE.Sprite(material);
        sprite.scale.set(1, 0.5, 1); // adjust size
        sprite.position.set(0, 0, -2); // position in front of user

        const xrHud = new THREE.Group();
        xrHud.add(sprite);
        this.camera.add(xrHud);
    }
}