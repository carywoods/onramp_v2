"""
Patch every school JSON with:
  - federally_recognized: true/false  (U.S. Dept of Education official HBCU list)
  - hbcu_designation_note: explanation for non-recognized or special cases
  - coordinates: {lat, lon}  (for proximity search)
  - region: one of Southeast, Mid-Atlantic, Midwest, Northeast, South Central,
             Southwest, West, Caribbean
  - institution_level: 4-year, 2-year, graduate-only, law-only

Run with: python patch_federal_and_coords.py
"""

import json
from pathlib import Path

KB_DIR = Path("kb/hbcu")
TODAY  = "2026-05-25"

# ---------------------------------------------------------------------------
# Official U.S. Dept of Education HBCU list (101 institutions as of 2024)
# school_id -> True means federally recognized
# ---------------------------------------------------------------------------
FEDERAL_RECOGNIZED = {
    "alabama_a_m_university",
    "alabama_state_university",
    "albany_state_university",
    "alcorn_state_university",
    "allen_university",
    "arkansas_baptist_college",
    "barber-scotia-college",
    "benedict_college",
    "bennett_college",
    "bethune_cookman_university",
    "bishop_state_community_college",
    "bluefield_state_college",          # now Bluefield State University
    "bowie_state_university",
    "central_state_university",
    "charles_r_drew_university_of_medicine_and_science",
    "cheyney_university_of_pennsylvania",
    "chicago_state_university",
    "claflin_university",
    "clark_atlanta_university",
    "clinton_college",
    "coahoma_community_college",
    "concordia-college-alabama",        # closed but was federally recognized
    "coppin_state_university",
    "delaware_state_university",
    "denmark_technical_college",
    "dillard_university",
    "edward_waters_university",
    "elizabeth_city_state_university",
    "fayetteville_state_university",
    "fisk_university",
    "florida_a_m_university",
    "florida_memorial_university",
    "fort_valley_state_university",
    "gadsden_state_community_college",
    "grambling_state_university",
    "hampton_university",
    "harris_stowe_state_university",
    "howard_university",
    "huston_tillotson_university",
    "interdenominational_theological_center",
    "j_f_drake_state_technical_college",
    "jackson_state_university",
    "jarvis_christian_college",         # now Jarvis Christian University
    "johnson_c_smith_university",
    "kentucky_state_university",
    "knoxville-college",
    "lane_college",
    "langston_university",
    "lawson_state_community_college",
    "lemoyne_owen_college",
    "lincoln_university_mo",
    "lincoln_university_pa",
    "livingstone_college",
    "medgar_evers_college",
    "meharry_medical_college",
    "miles_college",
    "mississippi_valley_state_university",
    "morehouse_college",
    "morehouse_school_of_medicine",
    "morgan_state_university",
    "morris_brown_college",
    "morris-college",
    "norfolk_state_university",
    "north_carolina_a_t_state_university",
    "north_carolina_central_university",
    "oakwood_university",
    "paine_college",
    "paul_quinn_college",
    "philander_smith_college",          # now Philander Smith University
    "prairie_view_a_m_university",
    "rust_college",
    "saint-paul-s-college",             # closed but was federally recognized
    "savannah_state_university",
    "selma_university",
    "shaw_university",
    "shelton_state_community_college",
    "shorter_college",
    "simmons_college_of_kentucky",
    "south_carolina_state_university",
    "southern_university_and_a_m_college",
    "southern_university_at_new_orleans",
    "southern_university_at_shreveport",
    "southern_university_law_center",
    "southwestern_christian_college",
    "spelman_college",
    "st_augustine_s_university",
    "st_philip_s_college",
    "stillman_college",
    "talladega_college",
    "tennessee_state_university",
    "texas_college",
    "texas_southern_university",
    "tougaloo_college",
    "trenholm_state_community_college",
    "tuskegee_university",
    "university_of_arkansas_at_pine_bluff",
    "university_of_maryland_eastern_shore",
    "university_of_the_district_of_columbia",
    "university_of_the_virgin_islands",
    "virginia_state_university",
    "virginia_union_university",
    "voorhees_college",                 # now Voorhees University
    "west_virginia_state_university",
    "wilberforce_university",
    "wiley_college",                    # now Wiley University
    "winston_salem_state_university",
    "xavier_university_of_louisiana",
}

# NOT on federal list — with explanation
NOT_RECOGNIZED_NOTES = {
    "martin-university":      "Closed 2025. Was never on the U.S. Dept of Education official HBCU list, though it served a predominantly Black urban population in Indianapolis.",
    "pensole_lewis_college":  "Founded 2020. A new institution focused on design and business; HBCU federal designation not yet granted as of 2025.",
    "virginia_university_of_lynchburg": "Operates as an HBCU and is recognized by the HBCU community, but does not currently appear on the U.S. Dept of Education official list.",
    "american_baptist_college": "A historically Black theological college recognized by the HBCU community. Not on the U.S. Dept of Education official HBCU designation list.",
    "chicago_state_university": "Founded to serve Chicago's South Side community; majority Black enrollment but not officially designated an HBCU by the U.S. Dept of Education.",
}

# ---------------------------------------------------------------------------
# Coordinates {lat, lon} and region for every school
# ---------------------------------------------------------------------------
SCHOOL_DATA = {
    "alabama_a_m_university":        {"lat": 34.7831, "lon": -86.5686, "region": "Southeast",     "institution_level": "4-year"},
    "alabama_state_university":      {"lat": 32.3668, "lon": -86.2950, "region": "Southeast",     "institution_level": "4-year"},
    "albany_state_university":       {"lat": 31.5785, "lon": -84.1557, "region": "Southeast",     "institution_level": "4-year"},
    "alcorn_state_university":       {"lat": 31.5440, "lon": -91.0463, "region": "Southeast",     "institution_level": "4-year"},
    "allen_university":              {"lat": 33.9994, "lon": -81.0337, "region": "Southeast",     "institution_level": "4-year"},
    "american_baptist_college":      {"lat": 36.1990, "lon": -86.7580, "region": "Southeast",     "institution_level": "4-year"},
    "arkansas_baptist_college":      {"lat": 34.7518, "lon": -92.2896, "region": "South Central", "institution_level": "4-year"},
    "barber-scotia-college":         {"lat": 35.3960, "lon": -80.5743, "region": "Southeast",     "institution_level": "4-year"},
    "benedict_college":              {"lat": 34.0007, "lon": -81.0290, "region": "Southeast",     "institution_level": "4-year"},
    "bennett_college":               {"lat": 36.0598, "lon": -79.7884, "region": "Southeast",     "institution_level": "4-year"},
    "bethune_cookman_university":    {"lat": 29.2163, "lon": -81.0228, "region": "Southeast",     "institution_level": "4-year"},
    "bishop_state_community_college":{"lat": 30.6780, "lon": -88.1058, "region": "Southeast",     "institution_level": "2-year"},
    "bluefield_state_college":       {"lat": 37.2698, "lon": -81.2215, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "bowie_state_university":        {"lat": 38.9537, "lon": -76.7291, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "central_state_university":      {"lat": 39.8017, "lon": -83.9810, "region": "Midwest",       "institution_level": "4-year"},
    "charles_r_drew_university_of_medicine_and_science": {"lat": 33.9228, "lon": -118.2434, "region": "West", "institution_level": "graduate-only"},
    "cheyney_university_of_pennsylvania": {"lat": 39.9318, "lon": -75.5185, "region": "Mid-Atlantic", "institution_level": "4-year"},
    "chicago_state_university":      {"lat": 41.7197, "lon": -87.6050, "region": "Midwest",       "institution_level": "4-year"},
    "claflin_university":            {"lat": 33.4957, "lon": -80.8567, "region": "Southeast",     "institution_level": "4-year"},
    "clark_atlanta_university":      {"lat": 33.7490, "lon": -84.4130, "region": "Southeast",     "institution_level": "4-year"},
    "clinton_college":               {"lat": 34.9249, "lon": -81.0251, "region": "Southeast",     "institution_level": "2-year"},
    "coahoma_community_college":     {"lat": 34.3645, "lon": -90.5743, "region": "Southeast",     "institution_level": "2-year"},
    "concordia-college-alabama":     {"lat": 32.5224, "lon": -87.8386, "region": "Southeast",     "institution_level": "4-year"},
    "coppin_state_university":       {"lat": 39.3126, "lon": -76.6697, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "delaware_state_university":     {"lat": 39.1557, "lon": -75.5243, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "denmark_technical_college":     {"lat": 33.3235, "lon": -81.1434, "region": "Southeast",     "institution_level": "2-year"},
    "dillard_university":            {"lat": 29.9871, "lon": -90.0715, "region": "South Central", "institution_level": "4-year"},
    "edward_waters_university":      {"lat": 30.3322, "lon": -81.6557, "region": "Southeast",     "institution_level": "4-year"},
    "elizabeth_city_state_university":{"lat": 36.2954, "lon": -76.2522, "region": "Southeast",   "institution_level": "4-year"},
    "fayetteville_state_university": {"lat": 35.0419, "lon": -78.9014, "region": "Southeast",     "institution_level": "4-year"},
    "fisk_university":               {"lat": 36.1680, "lon": -86.8104, "region": "Southeast",     "institution_level": "4-year"},
    "florida_a_m_university":        {"lat": 30.4202, "lon": -84.2968, "region": "Southeast",     "institution_level": "4-year"},
    "florida_memorial_university":   {"lat": 25.9420, "lon": -80.2456, "region": "Southeast",     "institution_level": "4-year"},
    "fort_valley_state_university":  {"lat": 32.5535, "lon": -83.8849, "region": "Southeast",     "institution_level": "4-year"},
    "gadsden_state_community_college":{"lat": 34.0143, "lon": -86.0066, "region": "Southeast",   "institution_level": "2-year"},
    "grambling_state_university":    {"lat": 32.5274, "lon": -92.7157, "region": "South Central", "institution_level": "4-year"},
    "hampton_university":            {"lat": 37.0241, "lon": -76.3458, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "harris_stowe_state_university": {"lat": 38.6351, "lon": -90.2490, "region": "Midwest",       "institution_level": "4-year"},
    "howard_university":             {"lat": 38.9222, "lon": -77.0202, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "huston_tillotson_university":   {"lat": 30.2724, "lon": -97.7226, "region": "South Central", "institution_level": "4-year"},
    "interdenominational_theological_center": {"lat": 33.7490, "lon": -84.4130, "region": "Southeast", "institution_level": "graduate-only"},
    "j_f_drake_state_technical_college": {"lat": 34.7431, "lon": -86.5850, "region": "Southeast", "institution_level": "2-year"},
    "jackson_state_university":      {"lat": 32.2988, "lon": -90.1848, "region": "Southeast",     "institution_level": "4-year"},
    "jarvis_christian_college":      {"lat": 32.2677, "lon": -94.8527, "region": "South Central", "institution_level": "4-year"},
    "johnson_c_smith_university":    {"lat": 35.2271, "lon": -80.8631, "region": "Southeast",     "institution_level": "4-year"},
    "kentucky_state_university":     {"lat": 38.1968, "lon": -84.8733, "region": "Southeast",     "institution_level": "4-year"},
    "knoxville-college":             {"lat": 35.9946, "lon": -83.9685, "region": "Southeast",     "institution_level": "4-year"},
    "lane_college":                  {"lat": 35.6151, "lon": -88.8340, "region": "Southeast",     "institution_level": "4-year"},
    "langston_university":           {"lat": 35.9365, "lon": -97.2628, "region": "South Central", "institution_level": "4-year"},
    "lawson_state_community_college":{"lat": 33.4527, "lon": -86.8127, "region": "Southeast",     "institution_level": "2-year"},
    "lemoyne_owen_college":          {"lat": 35.1049, "lon": -90.0490, "region": "Southeast",     "institution_level": "4-year"},
    "lincoln_university_mo":         {"lat": 38.5573, "lon": -92.1735, "region": "Midwest",       "institution_level": "4-year"},
    "lincoln_university_pa":         {"lat": 39.8082, "lon": -75.9277, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "livingstone_college":           {"lat": 35.6693, "lon": -80.4857, "region": "Southeast",     "institution_level": "4-year"},
    "martin-university":             {"lat": 39.7823, "lon": -86.1052, "region": "Midwest",       "institution_level": "4-year"},
    "medgar_evers_college":          {"lat": 40.6501, "lon": -73.9496, "region": "Northeast",     "institution_level": "4-year"},
    "meharry_medical_college":       {"lat": 36.1677, "lon": -86.8160, "region": "Southeast",     "institution_level": "graduate-only"},
    "miles_college":                 {"lat": 33.5065, "lon": -86.9341, "region": "Southeast",     "institution_level": "4-year"},
    "mississippi_valley_state_university": {"lat": 33.4943, "lon": -90.3265, "region": "Southeast", "institution_level": "4-year"},
    "morehouse_college":             {"lat": 33.7490, "lon": -84.4174, "region": "Southeast",     "institution_level": "4-year"},
    "morehouse_school_of_medicine":  {"lat": 33.7490, "lon": -84.4130, "region": "Southeast",     "institution_level": "graduate-only"},
    "morgan_state_university":       {"lat": 39.3432, "lon": -76.5838, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "morris_brown_college":          {"lat": 33.7557, "lon": -84.4152, "region": "Southeast",     "institution_level": "4-year"},
    "morris-college":                {"lat": 33.9346, "lon": -80.3473, "region": "Southeast",     "institution_level": "4-year"},
    "norfolk_state_university":      {"lat": 36.8468, "lon": -76.2791, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "north_carolina_a_t_state_university": {"lat": 36.0726, "lon": -79.7887, "region": "Southeast", "institution_level": "4-year"},
    "north_carolina_central_university": {"lat": 35.9779, "lon": -78.8997, "region": "Southeast", "institution_level": "4-year"},
    "oakwood_university":            {"lat": 34.7696, "lon": -86.7291, "region": "Southeast",     "institution_level": "4-year"},
    "paine_college":                 {"lat": 33.4651, "lon": -81.9743, "region": "Southeast",     "institution_level": "4-year"},
    "paul_quinn_college":            {"lat": 32.6721, "lon": -96.8147, "region": "South Central", "institution_level": "4-year"},
    "pensole_lewis_college":         {"lat": 42.3486, "lon": -83.0457, "region": "Midwest",       "institution_level": "4-year"},
    "philander_smith_college":       {"lat": 34.7465, "lon": -92.2896, "region": "South Central", "institution_level": "4-year"},
    "prairie_view_a_m_university":   {"lat": 30.0888, "lon": -95.9835, "region": "South Central", "institution_level": "4-year"},
    "rust_college":                  {"lat": 34.8454, "lon": -89.0145, "region": "Southeast",     "institution_level": "4-year"},
    "saint-paul-s-college":          {"lat": 36.7057, "lon": -78.1003, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "savannah_state_university":     {"lat": 32.0560, "lon": -81.0998, "region": "Southeast",     "institution_level": "4-year"},
    "selma_university":              {"lat": 32.4074, "lon": -87.0211, "region": "Southeast",     "institution_level": "4-year"},
    "shaw_university":               {"lat": 35.7721, "lon": -78.6374, "region": "Southeast",     "institution_level": "4-year"},
    "shelton_state_community_college":{"lat": 33.1845, "lon": -87.5558, "region": "Southeast",   "institution_level": "2-year"},
    "shorter_college":               {"lat": 35.2787, "lon": -92.4432, "region": "South Central", "institution_level": "2-year"},
    "simmons_college_of_kentucky":   {"lat": 38.2374, "lon": -85.7408, "region": "Southeast",     "institution_level": "4-year"},
    "south_carolina_state_university":{"lat": 33.4957, "lon": -80.8613, "region": "Southeast",   "institution_level": "4-year"},
    "southern_university_and_a_m_college": {"lat": 30.5266, "lon": -91.1871, "region": "South Central", "institution_level": "4-year"},
    "southern_university_at_new_orleans": {"lat": 30.0271, "lon": -90.0715, "region": "South Central", "institution_level": "4-year"},
    "southern_university_at_shreveport": {"lat": 32.4907, "lon": -93.7502, "region": "South Central", "institution_level": "2-year"},
    "southern_university_law_center":{"lat": 30.5266, "lon": -91.1871, "region": "South Central", "institution_level": "law-only"},
    "southwestern_christian_college":{"lat": 33.1290, "lon": -96.3527, "region": "South Central", "institution_level": "2-year"},
    "spelman_college":               {"lat": 33.7468, "lon": -84.4135, "region": "Southeast",     "institution_level": "4-year"},
    "st_augustine_s_university":     {"lat": 35.7943, "lon": -78.6374, "region": "Southeast",     "institution_level": "4-year"},
    "st_philip_s_college":           {"lat": 29.4124, "lon": -98.4766, "region": "South Central", "institution_level": "2-year"},
    "stillman_college":              {"lat": 33.1893, "lon": -87.5686, "region": "Southeast",     "institution_level": "4-year"},
    "talladega_college":             {"lat": 33.4318, "lon": -86.1049, "region": "Southeast",     "institution_level": "4-year"},
    "tennessee_state_university":    {"lat": 36.1677, "lon": -86.8685, "region": "Southeast",     "institution_level": "4-year"},
    "texas_college":                 {"lat": 32.3207, "lon": -95.3010, "region": "South Central", "institution_level": "4-year"},
    "texas_southern_university":     {"lat": 29.7218, "lon": -95.3496, "region": "South Central", "institution_level": "4-year"},
    "tougaloo_college":              {"lat": 32.4235, "lon": -90.1132, "region": "Southeast",     "institution_level": "4-year"},
    "trenholm_state_community_college":{"lat": 32.3668, "lon": -86.2950, "region": "Southeast",  "institution_level": "2-year"},
    "tuskegee_university":           {"lat": 32.4324, "lon": -85.7080, "region": "Southeast",     "institution_level": "4-year"},
    "university_of_arkansas_at_pine_bluff": {"lat": 34.2282, "lon": -92.0032, "region": "South Central", "institution_level": "4-year"},
    "university_of_maryland_eastern_shore": {"lat": 38.2107, "lon": -75.7152, "region": "Mid-Atlantic", "institution_level": "4-year"},
    "university_of_the_district_of_columbia": {"lat": 38.9432, "lon": -77.0635, "region": "Mid-Atlantic", "institution_level": "4-year"},
    "university_of_the_virgin_islands": {"lat": 18.3419, "lon": -64.9307, "region": "Caribbean", "institution_level": "4-year"},
    "virginia_state_university":     {"lat": 37.2324, "lon": -77.4052, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "virginia_union_university":     {"lat": 37.5668, "lon": -77.4366, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "virginia_university_of_lynchburg": {"lat": 37.4138, "lon": -79.1422, "region": "Mid-Atlantic", "institution_level": "4-year"},
    "voorhees_college":              {"lat": 33.3235, "lon": -81.1160, "region": "Southeast",     "institution_level": "4-year"},
    "west_virginia_state_university":{"lat": 38.4185, "lon": -81.7957, "region": "Mid-Atlantic",  "institution_level": "4-year"},
    "wilberforce_university":        {"lat": 39.7157, "lon": -83.8810, "region": "Midwest",       "institution_level": "4-year"},
    "wiley_college":                 {"lat": 32.5182, "lon": -94.3627, "region": "South Central", "institution_level": "4-year"},
    "winston_salem_state_university":{"lat": 36.0932, "lon": -80.2651, "region": "Southeast",     "institution_level": "4-year"},
    "xavier_university_of_louisiana":{"lat": 29.9588, "lon": -90.1204, "region": "South Central", "institution_level": "4-year"},
}


def main():
    files   = sorted(KB_DIR.glob("*.json"))
    updated = 0

    for fpath in files:
        with open(fpath) as f:
            data = json.load(f)

        school_id = data.get("school_id", fpath.stem)
        changed   = False

        # Federal recognition
        is_recognized = school_id in FEDERAL_RECOGNIZED
        if data.get("federally_recognized") != is_recognized:
            data["federally_recognized"] = is_recognized
            changed = True

        if not is_recognized and school_id in NOT_RECOGNIZED_NOTES:
            note = NOT_RECOGNIZED_NOTES[school_id]
            if data.get("hbcu_designation_note") != note:
                data["hbcu_designation_note"] = note
                changed = True
        elif not is_recognized and "hbcu_designation_note" not in data:
            data["hbcu_designation_note"] = (
                "This institution is not on the U.S. Department of Education's "
                "official HBCU designation list."
            )
            changed = True

        # Coordinates, region, institution level
        if school_id in SCHOOL_DATA:
            sd = SCHOOL_DATA[school_id]
            if data.get("coordinates") != {"lat": sd["lat"], "lon": sd["lon"]}:
                data["coordinates"] = {"lat": sd["lat"], "lon": sd["lon"]}
                changed = True
            if data.get("region") != sd["region"]:
                data["region"] = sd["region"]
                changed = True
            if data.get("institution_level") != sd["institution_level"]:
                data["institution_level"] = sd["institution_level"]
                changed = True

        if changed:
            data["last_updated"] = TODAY
            with open(fpath, "w") as f:
                json.dump(data, f, indent=2)
            fed_label = "FEDERAL" if is_recognized else "NOT-FEDERAL"
            print(f"[{fed_label}] {data.get('name', school_id)}")
            updated += 1

    print(f"\nDone — {updated} files updated")

    # Summary
    all_data  = [json.load(open(f)) for f in KB_DIR.glob("*.json")]
    fed_count = sum(1 for d in all_data if d.get("federally_recognized"))
    not_count = sum(1 for d in all_data if not d.get("federally_recognized"))
    print(f"Federally recognized: {fed_count}")
    print(f"Not on federal list:  {not_count}")


if __name__ == "__main__":
    main()
