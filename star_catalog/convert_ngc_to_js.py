import csv

# Input and output file paths
input_csvs = ['NGC.csv','NGC_addendum.csv']
output_js = 'ngcCatalog.js'

# Initialize the JavaScript array content
js_array = ['const ngcCatalog = [']

# Read the CSV file
for input_csv in input_csvs:
    with open(input_csv, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        
        # Process each row
        for row in reader:
            # Extract required fields
            # Dup = duplicate, *=star, **=double star, 
            if row['Type'] not in ['Dup','*','**','*Ass','NonEx','Other','Nova']:
                name = row['Name']
                type_ = row['Type']
                ra = row['RA']
                dec = row['Dec'].replace(':', '*', 1)  # Replace first colon with asterisk
                const = row['Const']
                b_mag = row['B-Mag']
                ang_size = row['MajAx']
                SurfBr = row['SurfBr']
                M = row['M']
                cname = row['Common names']
                # Format as JavaScript array element
                # Quote strings, keep B-Mag as number (float)
                js_entry = f'["{ra}","{dec}","{type_}",{b_mag},{SurfBr},{ang_size},"{const}","{name}","{cname}","{M}"]'
                js_array.append(js_entry + ',')

# Remove the last comma and close the array
js_array[-1] = js_array[-1].rstrip(',')
js_array.append('];')

# Write to JavaScript file
with open(output_js, 'w', encoding='utf-8') as jsfile:
    jsfile.write('\n'.join(js_array))

print(f"JavaScript array file '{output_js}' generated successfully.")