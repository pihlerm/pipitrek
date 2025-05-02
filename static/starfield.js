import * as THREE from 'three';
import { positionFromRADEC } from './astroutils.js';

export class Starfield {

    // r = 100.5;           // celestial sphere radius
    // maxMag = 6.5;        // Faintest magnitude for size scaling
    // baseSize = 1;        // Minimum size for faint stars
    // sizeScale = 0.35;    // Scale factor for size variation
    constructor(starfieldGroup) {
        this.starfieldGroup = starfieldGroup;    
    }

    addStarCatalog(starCatalog, minMagnitude = 5, r = 100.5, maxMag = 6.5, baseSize = 1, sizeScale = 0.35) {
        

        if (!starCatalog) return this.addRandomStars();

        const filteredCatalog = starCatalog.filter(star => {
            const mag = star[2];
            return mag <= minMagnitude; // Filter stars by magnitude
        });
        
        const starGeometry = new THREE.BufferGeometry();
        const starCount = filteredCatalog.length;
        const starPositions = new Float32Array(starCount * 3);
        const starSizes = new Float32Array(starCount); // Array for per-star sizes

        for (let i = 0; i < starCount; i++) {
            const [raStr, decStr, mag] = filteredCatalog[i];           
            const [x, y, z] = positionFromRADEC(raStr, decStr, this.starfieldGroup, r);
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

        return filteredCatalog;
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
}