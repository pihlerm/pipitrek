import * as THREE from 'three';
import * as AstroUtils from './astroutils.js';

export class Starfield {

    constructor(group) {
        this.group = group;
        this.catalogs = [];
        this.sphere = null;
        this.sphereRadius = 100.5;
        this.sphereIntersects = [];
        this.sphereIntersectionPoint = new THREE.Vector3();
        this.polygonLine = null;  
        this.polygonLineCenter = null;  

        this.imageCatalog = [];                                     // catalog of images to display on sphere
        this.imageCatalog.push([null, null, "Live", null, null]);   // add a dummy entry for the live image

        this._addCelestialSphere(this.sphereRadius);
    }

    enableCatalogs(type, enable) {
        if(type == 'image') {
            for(const entry of this.imageCatalog) {
                if(entry && entry[4] != null) entry[4].visible = enable;
            }
            return;
        }
        for(const entry of this.catalogs) {
            if(entry.type == type) {
                entry.object.visible = enable;
            }
        }
    }

    getEntryByObject(obj) {
        for(const entry of this.catalogs) {
            if(entry && entry.object == obj) return entry;
        }
        return null;
    }

    getCatalog(obj) {
        const entry = this.getEntryByObject(obj);
        return entry ? entry.catalog : null;
    }

    getLabelText(obj, index) {
        if(obj.name == 'image') {
            if(index < 0 || index >= this.imageCatalog.length || this.imageCatalog[index]==null) return null;
            const [,, name] = this.imageCatalog[index];
            return name;
        } else {
            const entry = this.getEntryByObject(obj);
            if(!entry) return null;
            const [raStr, decStr, type, visMAG, surfB, angSize, constStr, catNumber, name, M]  = entry.catalog[index];
            var retval = `${type} ${catNumber} ${visMAG} ${name}`;
            if(M != null && M!='') retval+= ` M${M}`;
            return retval;
        }
    }

    getWorldPosition(obj, index, vec) {       
        if(obj.name == 'image') {
            // image - compute world direction from image mesh
            obj.updateMatrixWorld(true);
            const v2 = new THREE.Vector3(0,0,1); // SphereGeometry faces +Z
            v2.applyQuaternion(obj.getWorldQuaternion(new THREE.Quaternion()));
            // Compute world position at radius r = sphereRadius add positional offset
            v2.multiplyScalar(this.sphereRadius);
            obj.getWorldPosition(vec); // get world position - sphere center
            vec.add(v2);
            return vec;
        } else {
            const entry = this.getEntryByObject(obj);
            if(!entry) return null;
            // Step 1: Get local position from buffer
            // Step 2: Apply group's world transform
            this.group.updateMatrixWorld(true); // Ensure world matrix is up-to-date
            vec.fromArray(entry.positions, index * 3).applyMatrix4(this.group.matrixWorld);
            return vec;
        }
    }

    
    addStarCatalog(cat, minMagnitude = 5) {    
        this.addCatalogMesh(
            cat.filter(g => {
                const [,, type, visMAG, surfB, angSize] = g;
                return visMAG <= minMagnitude && type == '*'; 
            }), 
            'star', 
            'stars');        
    }
    addGalaxyCatalog(cat, minMagnitude = 14) {
    
        this.addCatalogMesh(
            cat.filter(g => {
                const [,, type, visMAG, surfB, angSize] = g;
                return visMAG <= minMagnitude && ['G','Gpair','GTrpl','GGroup'].includes(type); 
            }), 
            'galaxy', 
            'NGC-galaxy');
        
    }
    addNebulaCatalog(cat, minMagnitude = 14) {    
        this.addCatalogMesh(
            cat.filter(g => {
                const [,, type, visMAG, surfB, angSize] = g;
                return visMAG <= minMagnitude && ['PN', 'HII', 'DrkN', 'EmN', 'Neb', 'RfN', 'SNR'].includes(type); 
            }), 
            'nebula', 
            'NGC-nebula');
        
    }
    addClusterCatalog(cat, minMagnitude = 14) {    
        this.addCatalogMesh(
            cat.filter(g => {
                const [,, type, visMAG, surfB, angSize] = g;
                return visMAG <= minMagnitude && ['OC1', 'GCl', 'Cl+N'].includes(type); 
            }), 
            'cluster', 
            'NGC-cluster');
        
    }

    async addImage(img, name, ra, dec, arcsecondsPerPixel, rotation = 0, index = null, widthArcsec = null) {
        const catalogIndex = (index == null ? this.imageCatalog.length : index);
        if(index == null) this.imageCatalog.push(null);
        const texture = await this.createImageTexture(img);
        const mesh = this.addImageMesh(texture, ra, dec, arcsecondsPerPixel, rotation, catalogIndex, widthArcsec);        
        this.imageCatalog[catalogIndex] = [ra, dec, name, texture, mesh ];
        return catalogIndex;
    }


    addLiveImage(imageb64, arcsecondsPerPixel, rotation = 0) {
        const blob = AstroUtils.base64ToBlob(imageb64);
        const url = URL.createObjectURL(blob);
        const dec = AstroUtils.Degrees(this.decAngle);
        const ra = AstroUtils.HoursMinutesSeconds(this.raAngle/15); 
        this.addImage(url, "Live Image", ra, dec, arcsecondsPerPixel, rotation, 0);
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
            this.imageCatalog[0][0] = AstroUtils.HoursMinutesSeconds(raHours);
            this.imageCatalog[0][1] = AstroUtils.Degrees(this.decAngle);
            const [x, y, z] = AstroUtils.positionFromRADECrad(raDeg* Math.PI / 180, 
                this.decAngle* Math.PI / 180, 
                this.group, this.sphereRadius, true);
            const target = new THREE.Vector3(x, y, z);
            this.imageCatalog[0][4].lookAt(target);    
        }
    }

    animateStars(elapsedTime) {
        return;
        if(this.starMaterial) {
            this.starMaterial.uniforms.uTime.value = elapsedTime;
        }
    }

    resetImageUniforms() {
        this._doToOneOrAllImages(null, obj => {
            const mesh = obj[4];
            if( mesh != null) {
                mesh.material.uniforms.gamma.value = 1;
                mesh.material.uniforms.transparency.value = 0.5;
                mesh.material.uniforms.brightness.value = 1;
                mesh.material.uniforms.showBorder.value = false;
            }
        });
    }
    
    highlightImages(index = null) {
        this._doToOneOrAllImages(index, obj => {
            const mesh = obj[4];
            if( mesh != null) {
                mesh.material.uniforms.gamma.value = 1.1;
                mesh.material.uniforms.transparency.value = 1;
                mesh.material.uniforms.brightness.value = 1;
                mesh.material.uniforms.showBorder.value = false;
            }
        });
    }

    markImages(index = null) {
        this._doToOneOrAllImages(index, obj => {
            if (obj[4] != null) {
                obj[4].material.uniforms.showBorder.value = true;
            }
        })
    }

    scaleImages(factor = null, index = null) {
        this._doToOneOrAllImages(index, obj => {
            if (obj[4] != null) {
                this._resizeMesh(obj[4], factor);
            }
        })
    }
    _doToOneOrAllImages(index = null, fn) {
        if(index != null && index >=0 && index < this.imageCatalog.length) {
            if(this.imageCatalog[index]) fn(this.imageCatalog[index]);
        } else {        
            this.imageCatalog.forEach((obj) => {if(obj) fn(obj);});
        }
    }

    _resizeMesh(mesh, factor) {
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

    _addCelestialSphere(r) {
        this.sphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), r);
    }
    
    _updatePolygonVisualization(close = false) {
        if ( this.polygonLine ) {
            this.group.remove( this.polygonLine );
            this.polygonLine.geometry.dispose();
            this.polygonLine.material.dispose();
            this.polygonLine = null;
        }
        const pts = this.sphereIntersects.map(v => v.clone().multiplyScalar(this.sphereRadius));  
        // close the loop
        if ( pts.length > 1 && close ) pts.push( pts[0].clone() );  
      
        const geo = new THREE.BufferGeometry().setFromPoints( pts );
        const mat = new THREE.LineBasicMaterial({ color: 0xff0000 });
        this.polygonLine = new THREE.Line( geo, mat );
        this.group.add( this.polygonLine );
    }

    clearSphereIntersecion() {
        this.sphereIntersects = [];
        if (this.polygonLine) {
            this.group.remove(this.polygonLine);
            this.polygonLine.geometry.dispose();
            this.polygonLine.material.dispose();
            this.polygonLine = null;
        }
    }

    sphereHit(worldRay) {
        if(!this.sphere) return null;
        // invert the group’s world‑matrix
        const invMat = new THREE.Matrix4().copy( this.group.matrixWorld ).invert();
        // clone & transform the ray into local space
        const localRay = new THREE.Ray();
        localRay.origin    = worldRay.origin.clone().applyMatrix4( invMat );
        localRay.direction = worldRay.direction.clone().transformDirection( invMat ).normalize();

        return localRay.intersectSphere(this.sphere, this.sphereIntersectionPoint);
    }

    // a world‐space Ray, transform it into group‐local
    addSphereIntersecion(worldRay) {

        const hit = this.sphereHit(worldRay);

        if (hit) {
            this.sphereIntersects.push(this.sphereIntersectionPoint.clone().normalize()); // store as unit vector
            this._updatePolygonVisualization(); // redraw polygon visually
        }
        return hit;
    }

    selectObjects(positions) {
        this.sphereIntersects = AstroUtils.makeSphericalPolygonConvex(this.sphereIntersects);
        if (!this.sphereIntersects || this.sphereIntersects.length < 3) {
            this.clearSphereIntersecion(); // clear the polygon if not enough points
            return []; // not enough points to form a polygon
        }
        this._updatePolygonVisualization(true); // redraw polygon visually
        this.polygonLineCenter = AstroUtils.getCenter(this.sphereIntersects).clone().multiplyScalar(this.sphereRadius); // for visualization
        const center = this.polygonLineCenter.clone().normalize(); // unit vector of center
        const selected = [];
        const pos = new THREE.Vector3();
        for (let i = 0; i < positions.length/3; i++) {
            pos.fromArray(positions, i * 3).normalize();
            const dist = center.dot(pos); // angular distance
            if (AstroUtils.isPointInConvexSphericalPolygon(pos, this.sphereIntersects)) {
                selected.push({index : i, distance: dist}); // Store index or object
            }
        }
        return selected;
    }

    select() {
        let selected = [];
        for (const entry of this.catalogs) {
            const sel = this.selectObjects(entry.positions);
            for(const obj of sel) {
                selected.push({object: entry.object, catalog: entry.catalog, index: obj.index, distance: obj.distance});
            }
        }
        selected.sort((a, b) => b.distance - a.distance); // Sort by distance
        return selected;
    }


    selectAt(worldRay, radiusDeg = 0.5) {

        const hit = this.sphereHit(worldRay);
        if (!hit) return [];
    
        const centerDir = this.sphereIntersectionPoint.clone().normalize(); // Unit vector of hit
    
        const selected = [];
        const cosThreshold = Math.cos(THREE.MathUtils.degToRad(radiusDeg));
        const pos = new THREE.Vector3();
    
        for (const entry of this.catalogs) {
            const selectedIndices = [];
            for (let i = 0; i < entry.positions.length / 3; i++) {
                pos.fromArray(entry.positions, i * 3).normalize();
    
                // Angular distance = dot product of unit vectors
                if (centerDir.dot(pos) >= cosThreshold) {
                    selectedIndices.push(i);
                }
            }
            for(const index of selectedIndices) {
                pos.fromArray(entry.positions, index * 3).normalize();
                selected.push({object: entry.object, catalog: entry.catalog, index: index, distance: centerDir.dot(pos)});
            }
        }
    
        selected.sort((a, b) => b.distance - a.distance); // Sort by distance
        return selected;
    }
    
    addCatalogMesh(catalog, type, name, r=null) {
        
        // for stars
        const maxMag = 6.5;
        const baseSize = 1;
        const sizeScale = 3.5;
        if(r == null) r = this.sphereRadius;
        const cnt = catalog.length;
        if (cnt === 0) return;
        
        const isStar = (type == 'star');
        
        let texture = null;
        switch(type) {
            case 'galaxy':
                texture = this.createGalaxyTexture();
                break;
            case 'nebula':
                texture = this.createNebulaTexture();
                break;
            case 'star':
                texture = this.createStarTexture();
                break;
            case 'cluster':
                texture = this.createStarClusterTexture();
                break;
            default:
                console.error('Unknown type:', type);
                return;
        }
        

        const geometry = new THREE.PlaneGeometry(1, 1);

        const material = new THREE.MeshBasicMaterial({
            map: texture,
            transparent: true,
            depthWrite: false,
            opacity: isStar ? 1 : 0.2,
            alphaTest: 0.1,
            blending: THREE.NormalBlending,
            vertexColors: true
          });
    
        const entry = {
            name: name,
            type: type,
            catalog: catalog, 
            positions:  new Float32Array(cnt * 3),
            object: new THREE.InstancedMesh(geometry, material, cnt),
            colorArray: new Float32Array(cnt * 3), // RGB per instance
        }

        entry.object.frustumCulled = false;
        
        geometry.setAttribute('color', new THREE.InstancedBufferAttribute( entry.colorArray, 3 ));

        const dummy = new THREE.Object3D();
    
        const arcminToRad = Math.PI / (180 * 60); // for angular size

        let minB = 26;
        let maxB = 0;  
        for (let i = 0; i < cnt; i++) {
            const [,,,,sb] = catalog[i];
            if(sb != null && sb != 0) {
                minB = Math.min(minB, sb);
                maxB = Math.max(maxB, sb);
            }        
        }
    
        for (let i = 0; i < cnt; i++) {
            const [raStr, decStr, type, visMAG, surfB, angSize, constStr, catNumber, name, M] = catalog[i];
            const [x, y, z] = AstroUtils.positionFromRADEC(raStr, decStr, this.group, r);

            entry.positions.set([x, y, z], i * 3);

            const angularSize = (isStar ? (baseSize + sizeScale * (maxMag - visMAG)) :  (angSize ?? 1));
            const angularRadiusRad = (angularSize / 2) * arcminToRad;
            const scale = 2 * r * Math.tan(angularRadiusRad); // total diameter
    
            dummy.position.set(x, y, z);
            dummy.lookAt(0, 0, 0);
            dummy.scale.set(scale, scale, scale);
            dummy.updateMatrix();
            entry.object.setMatrixAt(i, dummy.matrix);

            let brightness = 1.0;
            if(isStar) {
                brightness = 0.3 + 0.7*(maxMag - visMAG)/maxMag;
            } else {
                brightness = 1.0 - ((surfB ?? minB) -minB) / (maxB-minB);
            }
            
            brightness = Math.max(0.0, Math.min(1.0, brightness)); // Clamp to [0, 1]
            entry.colorArray.set([brightness, brightness, brightness], i * 3);
        }
    
        entry.object.name = 'catalog';
        this.group.add(entry.object);
        this.catalogs.push(entry);
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
        gradient.addColorStop(0.2, 'rgba(255, 255, 255, 0.8)');
        gradient.addColorStop(0.4, 'rgba(255, 255, 255, 0.4)');
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
    
        context.fillStyle = gradient;
        context.fillRect(0, 0, size, size);
    
        const texture = new THREE.CanvasTexture(canvas);
        return texture;
    }

    createGalaxyTexture() {
        const textureLoader = new THREE.TextureLoader();
        const texture = textureLoader.load('../static/img/galaxy.png', () => {
            console.log('Galaxy texture loaded:', texture.image.width, texture.image.height);
        });
        texture.colorSpace = THREE.SRGBColorSpace; // Ensure correct color rendering
        return texture;
    }

    createNebulaTexture() {
        const textureLoader = new THREE.TextureLoader();
        const texture = textureLoader.load('../static/img/nebula.png', () => {
            console.log('Nebula texture loaded:', texture.image.width, texture.image.height);
        });
        texture.colorSpace = THREE.SRGBColorSpace;
        return texture;
    }

    createStarClusterTexture() {
        const textureLoader = new THREE.TextureLoader();
        const texture = textureLoader.load('../static/img/cluster.png', () => {
            console.log('Cluster texture loaded:', texture.image.width, texture.image.height);
        });
        texture.colorSpace = THREE.SRGBColorSpace;
        return texture;
    }

    async createImageTexture(img) {
        const textureLoader = new THREE.TextureLoader();

        return new Promise((resolve, reject) => {
            textureLoader.load(
                img,
                (texture) => {
                    texture.flipY = false; // Adjust texture orientation if needed
                    texture.colorSpace = THREE.SRGBColorSpace; // Ensure correct color rendering
                    resolve(texture); // Resolve the promise with the loaded texture
                },
                undefined, // Optional: onProgress callback
                (error) => {
                    reject(error); // Reject the promise if an error occurs
                }
            );
        });
    }

    addImageMesh(texture, ra, dec, arcsecondsPerPixel, rotation, catalogIndex, widthArcsec = null) {
        // Now that texture is loaded, we know its size
        const imageWidth = texture.image.width;
        const imageHeight = texture.image.height;
        const r = this.sphereRadius-0.1; // radius of sphere - 0.1 to avoid z-fighting

        // Total size in arcseconds
        // Convert to radians
        let widthRad = 0;
        let heightRad = 0;
        if(widthArcsec == null) {
            widthRad = THREE.MathUtils.degToRad(imageWidth * arcsecondsPerPixel / 3600);
            heightRad = THREE.MathUtils.degToRad(imageHeight * arcsecondsPerPixel / 3600);
        } else {
            widthRad = THREE.MathUtils.degToRad(widthArcsec / 3600);
            heightRad = widthRad * imageHeight / imageWidth;
        }

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
        segmentMesh.name = "image";
        // Position
        const [x, y, z] = AstroUtils.positionFromRADEC(ra, dec, this.group);
        //segmentMesh.position.set(x, y, z);
        segmentMesh.position.set(0, 0, 0);

        // Rotate toward RA/Dec
        const target = new THREE.Vector3(x, y, z);
        segmentMesh.lookAt(target);

        // Adjust if needed
        segmentMesh.rotateZ(Math.PI-rotation);
        
        this.group.add(segmentMesh);

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
            side: THREE.DoubleSide,
            opacity: 0.5,
            alphaTest: 0.1,
            blending: THREE.NormalBlending            
        });
    }


    addStarCatalog2(starCatalog, minMagnitude = 5, r = 100.5, maxMag = 6.5, baseSize = 1, sizeScale = 0.35) {

        this.starCatalog = starCatalog.filter(star => {
            const mag = star[2];
            return mag <= minMagnitude; // Filter stars by magnitude
        });
        
        const starGeometry = new THREE.BufferGeometry();
        const starCount = this.starCatalog.length;
        this.starPositions = new Float32Array(starCount * 3);
        this.starSizes = new Float32Array(starCount); // Array for per-star sizes
        for (let i = 0; i < starCount; i++) {
            const [raStr, decStr, mag] = this.starCatalog[i];           
            const [x, y, z] = AstroUtils.positionFromRADEC(raStr, decStr, this.group, r);
            this.starPositions.set([x, y, z], i * 3);
            // Set size based on magnitude
            this.starSizes[i] = baseSize + sizeScale * (maxMag - mag);
        }
        starGeometry.setAttribute('position', new THREE.BufferAttribute(this.starPositions, 3));
        starGeometry.setAttribute('size', new THREE.BufferAttribute(this.starSizes, 1));

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
                    gl_PointSize = clamp(size * (300.0 / -mvPosition.z), 1.0, 100.0);
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

        this.stars = new THREE.Points(starGeometry, this.starMaterial);
        this.group.add(this.stars);
        this.stars.name = 'catalog';

        return this.starCatalog;
    }

}