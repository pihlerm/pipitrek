import re

def parse_bsc5p_line(line):
    """Parse a single line from BSC5P catalog and extract RA, Dec, Vmag."""
    
    sname = line[5:14].strip()   # Star name
    const = line[11:14].strip()  # Constellation
    HDnr  = line[25:31].strip()  # Henry Draper Catalog Number

    # RA J2000: bytes 76-83 (RAh: 76-77, RAm: 78-79, RAs: 80-83)
    rah = line[75:77].strip()  # I2
    ram = line[77:79].strip()  # I2
    ras = line[79:83].strip()  # F4.1
    
    # Dec J2000: bytes 84-90 (DE-: 84, DEd: 85-86, DEm: 87-88, DEs: 89-90)
    de_sign = line[83:84].strip()  # A1
    ded = line[84:86].strip()  # I2
    dem = line[86:88].strip()  # I2
    des = line[88:90].strip()  # I2
    
    # Vmag: bytes 103-107
    vmag = line[102:107].strip()  # F5.2
    
    # bv color
    bvcolor = line[110:114].strip()  # F5.2

    # Skip if any critical field is blank
    if not (rah and ram and ras and de_sign and ded and dem and des and vmag):
        print(f"Skipping line due to missing fields: {line.strip()}")
        return None
    
    try:
        # Parse numeric fields
        rah = int(rah)
        ram = int(ram)
        ras = float(ras)
        ded = int(ded)
        dem = int(dem)
        des = int(des)
        vmag = float(vmag)
        bvcolor = float(bvcolor)

        # Format RA as HH:MM:SS
        ra_str = f"{rah:02d}:{ram:02d}:{ras:04.1f}"
        
        # Format Dec as DD*MM:SS
        dec_str = f"{de_sign}{ded:02d}*{dem:02d}:{des:02d}"
        
        return [ra_str, dec_str, vmag, sname, const, HDnr, bvcolor]
    except (ValueError, TypeError):
        return None  # Skip lines with invalid numeric fields

def convert_bsc5p_to_js(input_file, output_file):
    """Convert BSC5P catalog to JavaScript starCatalog array."""
    stars = []
    
    # Read input file
    with open(input_file, 'r', encoding='ascii') as f:
        for line in f:
            star = parse_bsc5p_line(line)
            if star:
                stars.append(star)
    
    # Write to JavaScript file
    with open(output_file, 'w', encoding='ascii') as f:
        f.write('const starCatalog = [\n')
        for i, star in enumerate(stars):
            ra, dec, mag, name, constellation, HDnr, bvcolor = star
            # Escape quotes in strings and format the array element
            ra = ra.replace('"', '\\"')
            dec = dec.replace('"', '\\"')
            line = f'  ["{ra}","{dec}","*",{mag},0,0,"{constellation}","HD{HDnr}","{name}","",{bvcolor}]'
            if i < len(stars) - 1:
                line += ','
            f.write(line + '\n')
        f.write('];\n')
    
    print(f"Converted {len(stars)} stars to {output_file}")

if __name__ == '__main__':
    input_file = 'catalog.txt'  # Path to BSC5P catalog file
    output_file = 'starCatalog.js'  # Output JavaScript file
    convert_bsc5p_to_js(input_file, output_file)