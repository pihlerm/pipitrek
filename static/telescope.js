import * as THREE from 'three';
import {calculateLST, HoursMinutesSeconds, Degrees, parseRA, parseDec, positionFromRADEC, positionFromRADECrad } from './astroutils.js';

export class Telescope {
    constructor(scale, height) {
        this.westPier = false;          // True if telescope is on the west side of the pier
        this.telescopeScale = scale;      // Scale factor for telescope size
        this.telescopeFOV =2;           // FOV of the telescope camera
        this.height = height;
        this.tubeOffset = -1*this.telescopeScale;
         
        this.raAngle = 0;               // where the telescope is pointing, degrees 0 - 360
        this.decAngle = 0;              // where the telescope is pointing, degrees -90 - +90
        this.blockPointing = false;     // when simulating telescope pointing; block further pointing
         
        this.raAngleTarget = 0;         // telescope target angle, changes during animation
        this.decAngleTarget = 0;        // telescope target angle, changes during animation
        this._addTelescope();
        this._addProjectionScreen();
        // Initial angles
        this.setAngles(this.raAngle, this.decAngle);
        this.moveSound = null;
        this.tracking = false;

        this.cameraPosition = new THREE.Vector3();

        this.previousLST = null;
        this.currentLST = 0;
    }

    
    // render what telescope sees onto this.telescopeRenderTarget
    // the texture is then mapped onto this.projectionScreen

    renderScreen(renderer, scene) {
        const currentRenderTarget = renderer.getRenderTarget();
        const wasXREnabled = renderer.xr.enabled;
        const prevParent = this.projectionGroup.parent; 
        if(prevParent) prevParent.remove(this.projectionGroup);
        this.telescopeCamera.updateMatrixWorld(true);
        renderer.xr.enabled = false; // Disable XR to prevent head pose being applied
        renderer.setRenderTarget(this.telescopeRenderTarget);
        renderer.clear(); // clear before rendering
        renderer.render(scene, this.telescopeCamera);
        if(prevParent) prevParent.add(this.projectionGroup);
        renderer.xr.enabled = wasXREnabled; // Restore XR rendering for rest of scene
        renderer.setRenderTarget(currentRenderTarget);
    }

    getFOV() {
        return this.telescopeCamera.fov;
    }

    setFOV(fov) {
        this.telescopeCamera.fov = fov;
        this.telescopeCamera.updateProjectionMatrix(); // Apply the changes
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

    move(raDelta, decDelta) {
        this.raAngleTarget += raDelta;
        this.decAngleTarget += decDelta;
    }

    select(selected = true) {
        this.bodyMaterial.color.set(selected ? 0xff1111 : 0x2222aa);
    }

    setPolarAngle(angle) {
        this.polarGroup.rotation.z = angle;
    }
    
    setLST(lst) {
        this.currentLST = lst;
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
        let raDiff = raHours * 15 + 180;
        raDiff = ((raDiff % 360) + 360) % 360;
        if(animate) {
            this.animateToAngles(raDiff, decDegrees);
        } else {
            this.setAngles(raDiff, decDegrees);
        }
    }

    animate(addRaRotation) {
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

        // move backwards if not tracking
        if(!this.tracking && this.previousLST) {
            const dLST = (this.currentLST-this.previousLST) * 15;
            this.raAngle += dLST;
            this.raAngleTarget += dLST;
        }
        this.previousLST = this.currentLST;

        this.raGroup.rotation.y = this.raAngle * Math.PI / 180 - addRaRotation - this.currentLST* Math.PI / 12;
        this.decGroup.rotation.z = this.decAngle * Math.PI / 180;

        if(this.telescopeCamera) {
            this.telescopeCamera.updateMatrixWorld(true);
            this.telescopeCamera.getWorldPosition(this.cameraPosition);    
        }        

    }

    screenToEye(camera, renderer) {
        // Set to right eye
        for(const obj of this.projectionGroup.children) obj.layers.set(2);
        this.group.remove(this.projectionGroup);
        camera.add(this.projectionGroup);
        this.projectionGroup.position.set(0.055, -0.02, -0.15); // In front of camera, adjust as needed
        this.projectionGroup.scale.set(0.22,0.22,0.22);        
    }
    screenToScreen(camera, renderer) {
        for(const obj of this.projectionGroup.children) obj.layers.set(0);
        camera.remove(this.projectionGroup);
        this.group.add(this.projectionGroup);
        this.projectionGroup.position.set(1, this.height, 0); 
        this.projectionGroup.scale.set(1,1,1);
    }

    _addTelescope() {
        
        // Materials
        this.bodyMaterial = new THREE.MeshPhongMaterial({ color: 0x2222aa, shininess: 50 });
        this.axisMaterial = new THREE.MeshPhongMaterial({ color: 0xff0000, shininess: 50 });
        this.laserMaterial = new THREE.LineBasicMaterial({ color: 0x0000ff }); 
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
        
        this.group = new THREE.Group();
        this.group.name = "telescope";
        this.polarGroup = new THREE.Group();
        this.polarGroup.name = "polar";
        this.group.add(this.polarGroup);
        this.polarGroup.position.y = this.height;

        this.raGroup = new THREE.Group();
        this.raGroup.name = "ra";
        this.raGroup.position.y = bodyL/2;
        this.polarGroup.add(this.raGroup);

        this.decGroup = new THREE.Group();
        this.decGroup.name = "dec";
        this.raGroup.add(this.decGroup);

        // Vertical shaft
        const vshaftGeometry = new THREE.CylinderGeometry(shaftR, shaftR, this.height, 32);
        const vshaft = new THREE.Mesh(vshaftGeometry, this.bodyMaterial);
        vshaft.position.y = this.height / 2;
        vshaft.name = "vshaft";
        this.group.add(vshaft);


        // Polar axis - lower telescope body
        const raBodyGeometry = new THREE.CylinderGeometry(shaftR, shaftR, axleL, 32);
        const raBody = new THREE.Mesh(raBodyGeometry, this.bodyMaterial);
        raBody.name = "raBody";
        const polarAxisGeometry = new THREE.CylinderGeometry(axisR, axisR, axisL, 32);
        const polarAxis = new THREE.Mesh(polarAxisGeometry, this.axisMaterial);
        polarAxis.name = "polarAxis";
        this.polarGroup.add(raBody);
        //this.polarGroup.add(polarAxis);

        // Dec axis
        const decAxisGeometry = new THREE.CylinderGeometry(axisR, axisR, axisL, 32);
        const decAxis = new THREE.Mesh(decAxisGeometry, this.axisMaterial);
        decAxis.name = "decAxis";
        decAxis.rotation.x = Math.PI / 2;
        const decBodyGeometry = new THREE.CylinderGeometry(shaftR, shaftR, axleL, 32);
        const decBody = new THREE.Mesh(decBodyGeometry, this.bodyMaterial);
        decBody.name = "decBody";
        decBody.rotation.x = Math.PI / 2;
        this.raGroup.add(decBody);
        //this.raGroup.add(decAxis);

        // Counterweight shaft and weight
        const shaftGeometry = new THREE.CylinderGeometry(smallShaftR, smallShaftR, smallShaftL, 32);
        const shaft = new THREE.Mesh(shaftGeometry, this.shaftMaterial);
        shaft.name = "shaft";
        shaft.rotation.x = Math.PI / 2;
        shaft.position.z = smallShaftOffset;

        const weightGeometry = new THREE.CylinderGeometry(weightR, weightR, weightL, 32);
        const weight = new THREE.Mesh(weightGeometry, this.weightMaterial);
        weight.name = "weight";
        weight.rotation.x = Math.PI / 2;
        weight.position.z = weightOffset;

        const telescopeGeometry = new THREE.CylinderGeometry(tubeR, tubeR, tubeL, 32, 1, true);
        const telescope = new THREE.Mesh(telescopeGeometry, this.telescopeMaterial);
        telescope.name = "telescope";
        telescope.rotation.z = Math.PI *3 / 2;
        telescope.position.z = this.tubeOffset;

        const telescopeBackGeometry = new THREE.CylinderGeometry(tubeR*1.1, tubeR*1.1, tubeL*0.1, 32);
        const telescopeBack = new THREE.Mesh(telescopeBackGeometry, this.telescopeBackMaterial);
        telescopeBack.name = "telescopeBack";
        
        const laserGeometry = new THREE.BufferGeometry().setFromPoints([
            new THREE.Vector3(0, 0, this.tubeOffset),
            new THREE.Vector3(100, 0, this.tubeOffset)
        ]);        
        const laser = new THREE.Line(laserGeometry, this.laserMaterial);
        laser.name = "laser";

        telescopeBack.rotation.z = Math.PI / 2;
        telescopeBack.position.z = -tubeL/2;
        telescopeBack.position.x = -tubeL/2;
        this.decGroup.add(telescope);
        this.decGroup.add(telescopeBack);
        this.decGroup.add(shaft);
        this.decGroup.add(weight);
        this.decGroup.add(laser);
        
    }

    _addProjectionScreen() {
        // Create the telescope camera (narrow FOV simulating zoom)
        this.telescopeCamera = new THREE.PerspectiveCamera(this.telescopeFOV, 1, 0.1, 500);
        this.telescopeCamera.rotation.y = -Math.PI / 2; // Look down +X
        this.telescopeCamera.position.z = this.tubeOffset;
        this.telescopeCamera.name = "telescopeCamera";
        this.decGroup.add(this.telescopeCamera);

        this.telescopeRenderTarget = new THREE.WebGLRenderTarget(1024, 1024);

        // create telescope projection object
        const material2 = new THREE.ShaderMaterial({
            uniforms: {
                tDiffuse: { value: this.telescopeRenderTarget.texture },
            },
            vertexShader: `
                varying vec2 vUv;
                void main() {
                vUv = uv;
                gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                uniform sampler2D tDiffuse;
                varying vec2 vUv;

                void main() {
                vec2 center = vec2(0.5);
                float dist = distance(vUv, center);
                float vignette = smoothstep(0.5, 0.3, dist); // stronger toward edges
                vec4 texColor = texture2D(tDiffuse, vUv);
                gl_FragColor = vec4(texColor.rgb * vignette, texColor.a);
                }
            `,
            transparent: false,
            side: THREE.DoubleSide
        });

        // projection screen for telescope camera
        this.projectionScreen = new THREE.Mesh( new THREE.CircleGeometry(0.5, 64), material2);
        const shield = new THREE.Mesh( new THREE.CircleGeometry(0.8, 64), new THREE.MeshBasicMaterial({ color: 0x000000, side: THREE.DoubleSide}));
        this.projectionGroup = new THREE.Group();
        this.projectionGroup.position.set(1, this.height, 0); 
        this.projectionGroup.rotation.set(0, 0, Math.PI); // Reset rotation
        this.projectionGroup.name = "projectionScreen";
        shield.position.set(0, 0, -0.01); 
        //this.projectionGroup.add(shield);
        this.projectionGroup.add(this.projectionScreen);

        this.group.add(this.projectionGroup);

    }
}