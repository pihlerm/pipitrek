import * as THREE from 'three';

const maxButtons=6;
const menuButtonIndex=12;   // LEFT Meta Quest 2 controller's menu button is at index 12

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
        this.controller0 = renderer.xr.getController(0);
        this.controller1 = renderer.xr.getController(1);

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
                if(this.Right) {
                    console.log('Right controller already connected!');
                    return;
                }
                this.Right = controller;
                this.RightGamepad = event.data.gamepad || null; // <-- store gamepad reference!
                addLaser(controller, 0xff0000);
                userRig.add(controller);
                this.lastPositionR.copy(controller.position);
                if(this.onRConnectedCallback) this.onRConnectedCallback(controller);
            }
            if (handedness === 'left') {
                if(this.Left) {
                    console.log('Right controller already connected!');
                    return;
                }
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
        this.controller0.addEventListener('connected', onControllerConnected);
        this.controller1.addEventListener('connected', onControllerConnected); 
    }

    prepareCallbacks() {
        this.Rcallbacks = [];         
        this.Lcallbacks = [];
        this.onRConnectedCallback = null;
        this.onLConnectedCallback = null;
        this.menuPressedCallback = null;
        this.menuReleasedCallback = null;
        this.menuState = false;

        for(var i=0; i<maxButtons; i++) {
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

    onMenuPressed(callback) {
        this.menuPressedCallback = callback;
    }
    onMenuReleased(callback) {
        this.menuReleasedCallback = callback;
    }

    attachEvent(side, button, action, callback, interval=null) {
        
        if(button > maxButtons || button<0) throw new Error("Invalid argument: button must be between 0 and 7.");
        
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
        for(var i=0; i<buttons.length && i<maxButtons && i<state.length; i++) {
            const btn = buttons[i];
            const st = state[i];
            if(btn.pressed  && !st.pressed && time > (st.lastTime + st.interval)) {
                // console.log('Button:',i,buttons[i].pressed, state[i].pressed, time, state[i].lastTime, state[i].interval);
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
    
    handleMenuButton(btns) {
    // menu button is special
        if(btns.length >=menuButtonIndex && (this.menuPressedCallback || this.menuReleasedCallback)) {
            const btnmenu = btns[menuButtonIndex];
            if(btnmenu.pressed && !this.menuState) {
                this.menuState = true;
                if(this.menuPressedCallback) this.menuPressedCallback(btnmenu.pressed);
            } else if(!btnmenu.pressed && this.menuState) {
                this.menuState = false;
                if(this.menuReleasedCallback) this.menuReleasedCallback(btnmenu.pressed);
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
            const btns = this.LeftGamepad.buttons;
            this.handleButtons(time, btns, this.Lcallbacks);
            this.handleMenuButton(btns);
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


    /** * Check all buttons on the left controller and add labels to the scene.
     * @param {THREE.WebGLRenderer} renderer - The WebGL renderer instance.
     * @param {TelescopeSim} t - The TelescopeSim instance to add labels to.
     */
    checkAllButtons(renderer, t) {
        const session = renderer.xr.getSession();
        if (!session) return;

        for (const inputSource of session.inputSources) {
            if (inputSource.gamepad) {
                inputSource.gamepad.buttons.forEach((btn, i) => {
                    if (btn.pressed) {
                        console.log(`${inputSource.handedness} button ${i} is pressed`);
                        t.addCurrentLabel(new THREE.Vector3(2,2,2), `Left button ${i} is pressed`);
                    }
                });
            }
        }
    }


}