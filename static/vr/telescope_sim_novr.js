import * as THREE from 'three';
import {OrbitControls} from '../three/OrbitControls.js';
import * as AstroUtils from './astroutils.js';
import {Telescope} from './telescope.js';
import { getDefaultProperties } from './properties.js';


export class TelescopeSim {
    constructor(container, canvas) {
        this.container = container;
        this.canvas = canvas;
        this.settings = getDefaultProperties()
    }

    async init() {

        this.latitude = this.settings.latitude * Math.PI / 180,       // Rotates interactively
		this.longitude = this.settings.longitude;                     // Keep in degrees
        this.currentLST = AstroUtils.calculateLST(this.longitude);
        this.tempMatrix = new THREE.Matrix4();
        this.addRotation = 0;                           // Rotates RA interactively
        this.height = 1.6;

        this.addSceneAndLighting(this.canvas);
        
        this.telescope = new Telescope(1.0, this.height, this.scene);
        this.telescope.group.position.set(0,-this.height,0)

        // Start animation
        this.renderer.setAnimationLoop((time, frame) => this.animate(time, frame)); 

        this.addOrbitControls();
    }    
    

    pointTelescope(raStr, decStr, animate=false) {
        this.telescope.pointTelescope(raStr, decStr, animate);
    }
    meridianFlip() {
        this.telescope.meridianFlip();
    }

    setPier(west = false) {
        this.telescope.setPier(west);
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
        this.controls.maxDistance = 10;
        this.controls.enablePan = true;        
    }
    

    resize(width, height) {
        if(!this.camera || !this.renderer) return;
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate(time, frame) {
        
        // Update starfield rotation based on current LST
        this.currentLST = AstroUtils.calculateLST(this.longitude);
        this.telescope.setLST(this.currentLST);
        // update polar angle
        this.telescope.setPolarAngle(-(Math.PI / 2 - this.latitude));
        // animate telescope
        this.telescope.animate(this.addRotation);

        this.renderer.render(this.scene, this.camera);
    }

    addSceneAndLighting(canvas) {

        this.renderer = new THREE.WebGLRenderer({
             canvas: this.canvas,
             antialias: true,
             //logarithmicDepthBuffer: true,
             //alpha: true
        });

        this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);

        // Scene setup
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(50, canvas.clientWidth / canvas.clientHeight, 0.1, 50);
        //this.camera = new THREE.PerspectiveCamera(75, canvas.clientWidth / canvas.clientHeight, 0.1, 500);
        // Lighting
        this.ambientLight = new THREE.AmbientLight(0xffffff, 0.2);
        this.scene.add(this.ambientLight);
        
        this.directionalLight = new THREE.DirectionalLight(0xffffff, 5);
        this.directionalLight.position.set(-5, 5, 0);
        //this.scene.add(this.directionalLight);

        this.directionalLight2 = new THREE.DirectionalLight(0xffffff, 3);
        this.directionalLight2.position.set(1, 10, 0);
        this.scene.add(this.directionalLight2);

        // Groups
        this.camera.position.set(-4,1,4);  // non-VR
        
    }


}