    
    function frac(X) {
        X = X - Math.floor(X);
        if (X<0) X = X + 1.0;
        return X;		
    }

    export function validateRA(ra) {
        const raPattern = /^[0-2][0-9]:[0-5][0-9]:[0-5][0-9]$/;
        return raPattern.test(ra);
    }

    export function validateDEC(dec) {
        const decPattern = /^[+-][0-9][0-9]\*[0-5][0-9]:[0-5][0-9]$/;
        return decPattern.test(dec);
    }


    /**
     * Convert a decimal time value to a string representation in the format "hh:mm:ss".
     * @param {number} time - The decimal time value to convert.
     * @return {string} - The string representation of the decimal time value.
     */

    export function parseRA(raStr) {
        const [hours, minutes, seconds] = raStr.split(':').map(Number);
        return hours + minutes / 60 + seconds / 3600;
    }
    
    export function printRA (time) {
        var h = Math.floor(time);
        var min = Math.floor(60.0*frac(time));
        var secs = Math.round(60.0*(60.0*frac(time)-min)*10.0)/10.0;
        var str;
        if (min>=10) str=h+":"+min;
        else  str=h+":0"+min;
        if (secs<10) str = str + ":0"+secs;
        else str = str + ":"+secs;
        return " " + str;       
    }

    /**
     * Convert a decimal degree value to a string representation in the format "dd*mm:ss".
     * @param {number} degrees - The decimal degree value to convert.
     * @return {string} - The string representation of the decimal degree value.
     */

    export function printDEC(degrees) {
        const sign = degrees < 0 ? -1 : 1;
        const absDeg = Math.abs(degrees);

        const deg = Math.floor(absDeg);
        const minFloat = 60.0 * (absDeg - deg);
        const min = Math.floor(minFloat);
        const sec = Math.round(60.0 * (minFloat - min)*10.0)/10.0;

        const pad = (v) => (v < 10 ? '0' + v : v);
        
        const signedDeg = (sign == 1 ? '+' : '-') +  pad(deg);

        return `${signedDeg}*${pad(min)}:${pad(sec)}`;
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

    Object.assign(window, {
        validateRA,
        validateDEC,
        parseRA,
        parseDec,
        printRA,
        printDEC
    });