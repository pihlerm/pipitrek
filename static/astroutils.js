import * as THREE from 'three';

/**
* Convert a string representation of Right Ascension (RA) to decimal hours. 
* @param {string} raStr - The RA string in the format "hh:mm:ss".
* @return {number} - The decimal hours representation of RA.
* @throws {Error} - Throws an error if the input string is not in the correct format.
*/
export function parseRA(raStr) {
    const [hours, minutes, seconds] = raStr.split(':').map(Number);
    return hours + minutes / 60 + seconds / 3600;
}

/**
* Convert a string representation of Declination (Dec) to decimal degrees.
* @param {string} decStr - The Dec string in the format "±dd:mm:ss".
* @return {number} - The decimal degrees representation of Dec.
* @throws {Error} - Throws an error if the input string is not in the correct format.
*/
export function parseDec(decStr) {
    const match = decStr.match(/([+-]?\d+)\*(\d+):(\d+)/);
    if (!match) return 0;
    const degrees = parseInt(match[1]);
    const minutes = parseInt(match[2]);
    const seconds = parseInt(match[3]);
    const sign = degrees >= 0 ? 1 : -1;
    return degrees + sign * (minutes / 60 + seconds / 3600);
}

/** 
 * Calculate the Julian Date for a given date.
 * @param {Date} now - The date for which to calculate the Julian Date.
 * @return {number} - The Julian Date.
 * @throws {Error} - Throws an error if the input date is invalid.
 * @description The Julian Date is a continuous count of days since the beginning of the Julian Period on January 1, 4713 BC.
 * The Julian Date is used in astronomy and is useful for calculating time intervals between events.
 */
export function getJulianDate(now) {
    const year = now.getUTCFullYear();
    const month = now.getUTCMonth() + 1;
    const day = now.getUTCDate();
    const hours = now.getUTCHours() + now.getUTCMinutes() / 60 + (now.getUTCSeconds()+now.getUTCMilliseconds()/1000) / 3600;
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


function frac(X) {
    X = X - Math.floor(X);
    if (X<0) X = X + 1.0;
    return X;		
}

/**
 * Convert a decimal degree value to a string representation in the format "dd*mm:ss".
 * @param {number} degrees - The decimal degree value to convert.
 * @return {string} - The string representation of the decimal degree value.
 */
export function Degrees(degrees) {
    var deg = Math.floor(degrees);
    var min = Math.floor(60.0*frac(degrees));
    var secs = Math.round(60.0*(60.0*frac(degrees)-min));
    var str;
    if (min>=10) str=deg+"*"+min;
    else  str=deg+"*0"+min;
    if (secs<10) str = str + ":0"+secs;
    else str = str + ":"+secs;
    return str;       
}

/**
 * Convert a decimal time value to a string representation in the format "hh:mm:ss".
 * @param {number} time - The decimal time value to convert.
 * @return {string} - The string representation of the decimal time value.
 */
export function HoursMinutesSeconds(time) {
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
   
/**
 * Calculate the Local Sidereal Time (LST) based on the given longitude in degrees.
 * @param {number} longitudeDegrees - The longitude in degrees.
 * @return {number} - The Local Sidereal Time in hours.
 * @throws {Error} - Throws an error if the input longitude is invalid.
 */

 export function calculateLST(longitudeDegrees) {
    const now = new Date(); // browser time (assumed UTC or converted below)
    const JD = getJulianDate(now);
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

/**
 * Convert a string representation of Right Ascension (RA) and Declination (Dec) to a 3D position vector on a sphere.
 * @param {string} raStr - The RA string in the format "hh:mm:ss".
 * @param {string} decStr - The Dec string in the format "±dd*mm:ss".
 * @param {THREE.Group} group - The THREE.Group object relative to which raStr/decStr are given.
 * @param {number} r - The radius of the sphere (default is 100).
 * @param {boolean} world - If true, the position will be transformed from group to world coordinates (default is false).
 * @return {number[]} - The 3D position vector [x, y, z].
 * @throws {Error} - Throws an error if the input strings are not in the correct format.
 */
export function positionFromRADEC(raStr, decStr, group, r=100, world=false) {
    const ra = parseRA(raStr)/12 * Math.PI; // Hours to radians
    const dec = parseDec(decStr)/180 * Math.PI; // Degrees to radians
    return positionFromRADECrad(ra, dec, group, r, world);
}

export function positionFromRADECrad(ra, dec, group, r=100, world=false) {
    // Set position
    var pos = [];
    pos[0] = -r * Math.cos(ra)*Math.cos(dec); // -x
    pos[1] = r * Math.sin(dec); // y
    pos[2] = r * Math.sin(ra) * Math.cos(dec); // z
    if(world) {
        const v = new THREE.Vector3(pos[0], pos[1], pos[2]);
        group.updateMatrixWorld(true);
        v.applyMatrix4(group.matrixWorld);
        pos[0] = v.x;
        pos[1] = v.y;
        pos[2] = v.z;
    }
    return pos;
}


/*
    * Compute the center of a set of points in 3D space.
    * @param {THREE.Vector3[]} P - Array of THREE.Vector3 points.
    * @returns {THREE.Vector3} - The center point.
    */

export function getCenter(P) {
    const center = new THREE.Vector3();
    for (let v of P) center.add(v);
    center.divideScalar(P.length);
    return center;
}
/**
 * Replace this.sphereIntersects with its convex hull (spherical).
 * Uses tangent‑plane projection + 2D convex hull.
 */
export function makeSphericalPolygonConvex(P) {
    
    const n = P.length;
    if (n < 3) return null;                // fewer than 3 points is already “convex”

    // 1) find average direction
    const center = getCenter(P).normalize(); // center of polygon

    // 2) build orthonormal basis (u,v) tangent at center
    //    choose any vector not colinear with center
    const arbitrary = Math.abs(center.x) < 0.9 ? new THREE.Vector3(1,0,0) : new THREE.Vector3(0,1,0);

    const u = new THREE.Vector3().crossVectors(arbitrary, center).normalize();
    const v = new THREE.Vector3().crossVectors(center, u).normalize();

    // 3) project each Vi onto (u,v) plane → 2D coords
    const pts2D = P.map(V => {
        return {
            x: V.dot(u),
            y: V.dot(v),
            orig: V
        };
    });

    // 4) compute 2D convex hull by Andrew’s monotone chain
    pts2D.sort((a,b)=> a.x===b.x ? a.y-b.y : a.x-b.x);
    const cross = (o,a,b) => (a.x-o.x)*(b.y-o.y) - (a.y-o.y)*(b.x-o.x);

    const lower = [];
    for (let p of pts2D) {
        while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) {
            lower.pop();
        }
        lower.push(p);
    }
    const upper = [];
    for (let i=pts2D.length-1; i>=0; i--) {
        const p = pts2D[i];
        while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) {
            upper.pop();
        }
        upper.push(p);
    }
    upper.shift(); lower.pop();
    const hull2D = lower.concat(upper);

    // 5) rebuild sphereIntersects in hull order
    return hull2D.map(p=> p.orig );
}

export function isPointInConvexSphericalPolygon( P /*THREE.Vector3 unit*/, polyVerts ) {
    const m = polyVerts.length;
    for ( let i = 0; i < m; ++i ) {
        // grab edge endpoints
        const A = polyVerts[i];
        const B = polyVerts[(i+1)%m];
        // great‑circle normal:
        const N = new THREE.Vector3().crossVectors( A, B ).normalize();
        // if P is “behind” this edge, reject
        if ( N.dot(P) < 0 ) return false;
    }
    return true;
}


export function base64ToBlob(base64, mime = 'image/jpeg') {
    const binary = atob(base64);
    const len = binary.length;
    const buffer = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        buffer[i] = binary.charCodeAt(i);
    }
    return new Blob([buffer], { type: mime });
}

