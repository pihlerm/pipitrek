import * as THREE from 'three';

export function parseRA(raStr) {
    const [hours, minutes, seconds] = raStr.split(':').map(Number);
    return hours + minutes / 60 + seconds / 3600;
}

export function parseDec(decStr) {
    const match = decStr.match(/([+-]?\d+)\*(\d+):(\d+)/);
    if (!match) return 0;
    const degrees = parseInt(match[1]);
    const minutes = parseInt(match[2]);
    const seconds = parseInt(match[3]);
    const sign = degrees >= 0 ? 1 : -1;
    return degrees + sign * (minutes / 60 + seconds / 3600);
}

export function getJulianDate(now) {
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


function frac(X) {
    X = X - Math.floor(X);
    if (X<0) X = X + 1.0;
    return X;		
}

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
