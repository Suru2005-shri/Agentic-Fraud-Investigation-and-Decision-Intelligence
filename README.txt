POLARLOGIX - UI prototype (SIH 2026, PS 26062)
===============================================

KAISE KHOLNE HAI
  index.html pe double-click karo. Chrome / Edge / Firefox mein khulta hai.
  Internet nahi chahiye, koi install nahi. Sab kuch ek hi file mein hai.

DEMO CHALANE KE LIYE
  Top bar mein "Demo steps" dabao. 8 steps ek ek karke chalte hain:
  offline jao -> check-in -> sync -> SAR scenario -> route risk -> cold-chain -> AI.

FOLDER
  index.html            prototype (yehi kholna hai)
  source/template.html  editable source (UI, CSS, JS). Map data ki jagah __MAPDATA__ likha hai
  source/mapdata.json   Antarctica coastline (Natural Earth 1:50m) polar stereographic mein
  source/build_map.py   mapdata.json banane ki script (Natural Earth geojson chahiye)
  source/build.py       template.html + mapdata.json se index.html dubara banata hai

APNA BANANE KE LIYE
  Colours:  template.html ke upar :root { --navy, --blue, --red ... } badlo.
  Text:     MISS, ASSETS, PEOPLE, QA arrays mein.
  Logo:     <div class="logo-box"> ke andar svg badlo.
  Badalne ke baad:  python source/build.py   (ya seedha index.html edit kar lo)

PROTOTYPE KI LIMITS (judge ko khud bata do)
  - Backend nahi hai. Sab data hard-coded aur synthetic hai.
  - SAT COMM button ek simulation hai, asli offline nahi. Page refresh karne pe queue chali jaati hai.
  - Map static SVG hai (coastline asli hai). Sea-ice / weather layer load nahi hoti.
  - Sandhi ki exact location confirm nahi, isliye "planned" likha hai.
  - Risk score aur SAR grid simulation hain, validated nahi.
  - Cargo rules (1,500-1,800 kg air limit, hazardous cargo air se nahi) NCPOR ke
    ISEA advertisements se liye hain. Real use se pehle current advisory dekho.

CREDITS
  Coastline: Natural Earth (public domain). Fonts: system fonts.
