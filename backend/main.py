"""
GreenPath FastAPI Application.
Contrail-aware flight path optimization with NSGA-II.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict
from datetime import datetime
import logging
import time as _time

from fuel_model import (
    AIRCRAFT, altitude_band_to_ft, altitude_band_to_pressure,
    haversine_distance_km
)
from noaa_gfs import fetch_gfs_data
from nsga2_optimizer import (
    run_nsga2, select_by_weights, great_circle_waypoints,
    interpolate_path, f1_co2, f2_contrail_ef, f3_time
)
from issr_detector import get_issr_at_point, generate_atmosphere_sample
from sac_engine import check_contrail_formation

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("greenpath")

app = FastAPI(
    title="GreenPath API",
    description="Contrail-Aware Flight Path Optimization using NSGA-II",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Airport Database (500 entries) ───────────────────────────────────────────
AIRPORTS = {
    "JFK": (40.6413, -73.7781, "John F. Kennedy International"),
    "LHR": (51.4700, -0.4543, "London Heathrow"),
    "LAX": (33.9425, -118.4081, "Los Angeles International"),
    "NRT": (35.7647, 140.3864, "Tokyo Narita"),
    "DXB": (25.2532, 55.3657, "Dubai International"),
    "SYD": (-33.9461, 151.1772, "Sydney Kingsford Smith"),
    "CDG": (49.0097, 2.5479, "Paris Charles de Gaulle"),
    "FRA": (50.0379, 8.5622, "Frankfurt am Main"),
    "SIN": (1.3644, 103.9915, "Singapore Changi"),
    "HKG": (22.3080, 113.9185, "Hong Kong International"),
    "PEK": (40.0799, 116.6031, "Beijing Capital"),
    "ORD": (41.9742, -87.9073, "Chicago O'Hare"),
    "ATL": (33.6407, -84.4277, "Atlanta Hartsfield-Jackson"),
    "AMS": (52.3105, 4.7683, "Amsterdam Schiphol"),
    "ICN": (37.4602, 126.4407, "Seoul Incheon"),
    "MUC": (48.3538, 11.7861, "Munich"),
    "IST": (41.2753, 28.7519, "Istanbul"),
    "SFO": (37.6213, -122.3790, "San Francisco International"),
    "MIA": (25.7959, -80.2870, "Miami International"),
    "BOM": (19.0896, 72.8656, "Mumbai Chhatrapati Shivaji"),
    "DEL": (28.5562, 77.1000, "Indira Gandhi International"),
    "BKK": (13.6900, 100.7501, "Bangkok Suvarnabhumi"),
    "KUL": (2.7456, 101.7099, "Kuala Lumpur International"),
    "MAD": (40.4983, -3.5676, "Madrid Barajas"),
    "BCN": (41.2971, 2.0785, "Barcelona El Prat"),
    "FCO": (41.8003, 12.2389, "Rome Fiumicino"),
    "MEX": (19.4363, -99.0721, "Mexico City International"),
    "GRU": (-23.4356, -46.4731, "São Paulo Guarulhos"),
    "EZE": (-34.8222, -58.5358, "Buenos Aires Ezeiza"),
    "JNB": (-26.1392, 28.2460, "Johannesburg O.R. Tambo"),
    "CPT": (-33.9715, 18.6021, "Cape Town International"),
    "CAI": (30.1219, 31.4056, "Cairo International"),
    "DOH": (25.2731, 51.6081, "Doha Hamad International"),
    "AUH": (24.4330, 54.6511, "Abu Dhabi International"),
    "DEN": (39.8561, -104.6737, "Denver International"),
    "DFW": (32.8998, -97.0403, "Dallas/Fort Worth"),
    "SEA": (47.4502, -122.3088, "Seattle-Tacoma"),
    "IAH": (29.9844, -95.3414, "Houston George Bush"),
    "BOS": (42.3656, -71.0096, "Boston Logan"),
    "EWR": (40.6895, -74.1745, "Newark Liberty"),
    "IAD": (38.9531, -77.4565, "Washington Dulles"),
    "MSP": (44.8848, -93.2223, "Minneapolis-Saint Paul"),
    "DTW": (42.2162, -83.3554, "Detroit Metro"),
    "PHX": (33.4373, -112.0078, "Phoenix Sky Harbor"),
    "MCO": (28.4312, -81.3081, "Orlando International"),
    "CLT": (35.2140, -80.9431, "Charlotte Douglas"),
    "LAS": (36.0840, -115.1537, "Las Vegas Harry Reid"),
    "PHL": (39.8744, -75.2424, "Philadelphia International"),
    "SAN": (32.7338, -117.1933, "San Diego International"),
    "PDX": (45.5898, -122.5951, "Portland International"),
    "BWI": (39.1754, -76.6684, "Baltimore/Washington"),
    "TPA": (27.9756, -82.5332, "Tampa International"),
    "MCI": (39.2976, -94.7139, "Kansas City International"),
    "STL": (38.7487, -90.3700, "St. Louis Lambert"),
    "HNL": (21.3187, -157.9224, "Honolulu Daniel K. Inouye"),
    "ANC": (61.1741, -149.9962, "Anchorage Ted Stevens"),
    "YYZ": (43.6777, -79.6248, "Toronto Pearson"),
    "YVR": (49.1947, -123.1790, "Vancouver International"),
    "YUL": (45.4706, -73.7408, "Montreal Trudeau"),
    "LGW": (51.1537, -0.1821, "London Gatwick"),
    "STN": (51.8860, 0.2389, "London Stansted"),
    "MAN": (53.3537, -2.2750, "Manchester"),
    "EDI": (55.9508, -3.3725, "Edinburgh"),
    "DUB": (53.4264, -6.2499, "Dublin"),
    "ZRH": (47.4582, 8.5555, "Zurich"),
    "VIE": (48.1103, 16.5697, "Vienna"),
    "CPH": (55.6180, 12.6508, "Copenhagen Kastrup"),
    "ARN": (59.6498, 17.9238, "Stockholm Arlanda"),
    "OSL": (60.1976, 11.1004, "Oslo Gardermoen"),
    "HEL": (60.3172, 24.9633, "Helsinki Vantaa"),
    "WAW": (52.1672, 20.9679, "Warsaw Chopin"),
    "PRG": (50.1008, 14.2600, "Prague Vaclav Havel"),
    "BUD": (47.4389, 19.2556, "Budapest Ferenc Liszt"),
    "ATH": (37.9364, 23.9475, "Athens Eleftherios Venizelos"),
    "LIS": (38.7756, -9.1354, "Lisbon Humberto Delgado"),
    "OPO": (41.2481, -8.6814, "Porto"),
    "BRU": (50.9014, 4.4844, "Brussels"),
    "GVA": (46.2380, 6.1089, "Geneva"),
    "MXP": (45.6306, 8.7281, "Milan Malpensa"),
    "NAP": (40.8860, 14.2908, "Naples"),
    "TXL": (52.5597, 13.2877, "Berlin"),
    "BER": (52.3667, 13.5033, "Berlin Brandenburg"),
    "HAM": (53.6304, 9.9882, "Hamburg"),
    "PMI": (39.5517, 2.7388, "Palma de Mallorca"),
    "AGP": (36.6749, -4.4991, "Malaga"),
    "NCE": (43.6584, 7.2159, "Nice Côte d'Azur"),
    "MRS": (43.4393, 5.2214, "Marseille Provence"),
    "SVO": (55.9726, 37.4146, "Moscow Sheremetyevo"),
    "DME": (55.4088, 37.9063, "Moscow Domodedovo"),
    "LED": (59.8003, 30.2625, "St. Petersburg Pulkovo"),
    "PVG": (31.1443, 121.8083, "Shanghai Pudong"),
    "CAN": (23.3924, 113.2988, "Guangzhou Baiyun"),
    "CTU": (30.5785, 103.9471, "Chengdu Tianfu"),
    "SZX": (22.6393, 113.8107, "Shenzhen Bao'an"),
    "TPE": (25.0797, 121.2342, "Taipei Taoyuan"),
    "KIX": (34.4320, 135.2304, "Osaka Kansai"),
    "HND": (35.5494, 139.7798, "Tokyo Haneda"),
    "NGO": (34.8584, 136.8051, "Nagoya Chubu"),
    "MNL": (14.5086, 121.0194, "Manila Ninoy Aquino"),
    "CGK": (6.1256, 106.6558, "Jakarta Soekarno-Hatta"),
    "DPS": (-8.7482, 115.1672, "Bali Ngurah Rai"),
    "BNE": (-27.3842, 153.1175, "Brisbane"),
    "MEL": (-37.6690, 144.8410, "Melbourne Tullamarine"),
    "PER": (-31.9403, 115.9672, "Perth"),
    "AKL": (-37.0082, 174.7850, "Auckland"),
    "WLG": (-41.3272, 174.8053, "Wellington"),
    "NBO": (-1.3192, 36.9278, "Nairobi Jomo Kenyatta"),
    "LOS": (6.5774, 3.3211, "Lagos Murtala Muhammed"),
    "ADD": (8.9779, 38.7993, "Addis Ababa Bole"),
    "CMN": (33.3675, -7.5900, "Casablanca Mohammed V"),
    "TUN": (36.8510, 10.2272, "Tunis Carthage"),
    "ALG": (36.6910, 3.2154, "Algiers Houari Boumedienne"),
    "LIM": (-12.0219, -77.1143, "Lima Jorge Chavez"),
    "BOG": (4.7016, -74.1469, "Bogota El Dorado"),
    "SCL": (-33.3930, -70.7858, "Santiago Arturo Merino Benitez"),
    "GIG": (-22.8100, -43.2506, "Rio de Janeiro Galeao"),
    "CUN": (21.0365, -86.8771, "Cancun International"),
    "PTY": (9.0714, -79.3835, "Panama City Tocumen"),
    "SJO": (9.9939, -84.2088, "San Jose Juan Santamaria"),
    "HAV": (22.9892, -82.4091, "Havana Jose Marti"),
    "KWI": (29.2266, 47.9689, "Kuwait International"),
    "BAH": (26.2708, 50.6336, "Bahrain International"),
    "MCT": (23.5933, 58.2844, "Muscat International"),
    "RUH": (24.9576, 46.6988, "Riyadh King Khalid"),
    "JED": (21.6796, 39.1565, "Jeddah King Abdulaziz"),
    "AMM": (31.7226, 35.9932, "Amman Queen Alia"),
    "TLV": (32.0114, 34.8867, "Tel Aviv Ben Gurion"),
    "THR": (35.6893, 51.3114, "Tehran Imam Khomeini"),
    "ISB": (33.6167, 73.0991, "Islamabad International"),
    "KHI": (24.9065, 67.1610, "Karachi Jinnah"),
    "LHE": (31.5216, 74.4036, "Lahore Allama Iqbal"),
    "DAC": (23.8433, 90.3978, "Dhaka Hazrat Shahjalal"),
    "CMB": (7.1808, 79.8841, "Colombo Bandaranaike"),
    "MLE": (4.1915, 73.5291, "Male Velana International"),
    "KTM": (27.6966, 85.3591, "Kathmandu Tribhuvan"),
    "RGN": (16.9073, 96.1332, "Yangon International"),
    "SGN": (10.8188, 106.6520, "Ho Chi Minh City Tan Son Nhat"),
    "HAN": (21.2212, 105.8070, "Hanoi Noi Bai"),
    "REP": (13.4107, 107.8615, "Siem Reap Angkor"),
    "PNH": (11.5466, 104.8441, "Phnom Penh"),
    "VTE": (17.9883, 102.5633, "Vientiane Wattay"),
    "ULN": (47.8431, 106.7667, "Ulaanbaatar Chinggis Khaan"),
    "TAS": (41.2581, 69.2812, "Tashkent Islam Karimov"),
    "ALA": (43.3521, 77.0405, "Almaty International"),
    "NQZ": (51.0222, 71.4669, "Nur-Sultan Nursultan Nazarbayev"),
    "GYD": (40.4675, 50.0467, "Baku Heydar Aliyev"),
    "TBS": (41.6692, 44.9547, "Tbilisi Shota Rustaveli"),
    "EVN": (40.1473, 44.3959, "Yerevan Zvartnots"),
    "OTP": (44.5722, 26.1022, "Bucharest Henri Coanda"),
    "SOF": (42.6952, 23.4062, "Sofia"),
    "BEG": (44.8184, 20.3091, "Belgrade Nikola Tesla"),
    "ZAG": (45.7429, 16.0688, "Zagreb Franjo Tudjman"),
    "LJU": (46.2237, 14.4576, "Ljubljana Joze Pucnik"),
    "SKP": (41.9618, 21.6214, "Skopje Alexander the Great"),
    "TIA": (41.4147, 19.7206, "Tirana Mother Teresa"),
    "RIX": (56.9236, 23.9711, "Riga International"),
    "VNO": (54.6341, 25.2858, "Vilnius"),
    "TLL": (59.4133, 24.8328, "Tallinn Lennart Meri"),
    "KRK": (50.0777, 19.7848, "Krakow John Paul II"),
    "GDN": (54.3776, 18.4662, "Gdansk Lech Walesa"),
    "CLJ": (46.7852, 23.6862, "Cluj-Napoca"),
    "SPU": (43.5389, 16.2980, "Split"),
    "DBV": (42.5614, 18.2682, "Dubrovnik"),
    "SKG": (40.5197, 22.9709, "Thessaloniki Macedonia"),
    "HER": (35.3397, 25.1803, "Heraklion Nikos Kazantzakis"),
    "SAW": (40.8986, 29.3092, "Istanbul Sabiha Gokcen"),
    "AYT": (36.8987, 30.8005, "Antalya"),
    "ESB": (40.1281, 32.9951, "Ankara Esenboga"),
    "ADB": (38.2924, 27.1570, "Izmir Adnan Menderes"),
    "SSH": (27.9773, 34.3950, "Sharm El Sheikh"),
    "HRG": (27.1783, 33.7994, "Hurghada"),
    "LXR": (25.6710, 32.7066, "Luxor International"),
    "CMN": (33.3675, -7.5900, "Casablanca Mohammed V"),
    "RAK": (31.6069, -8.0363, "Marrakech Menara"),
    "FEZ": (33.9273, -4.9780, "Fez Saiss"),
    "ACC": (5.6052, -0.1668, "Accra Kotoka"),
    "ABJ": (5.2614, -3.9263, "Abidjan Felix Houphouet-Boigny"),
    "DKR": (14.7397, -17.4902, "Dakar Blaise Diagne"),
    "DAR": (-6.8781, 39.2026, "Dar es Salaam Julius Nyerere"),
    "EBB": (0.0424, 32.4435, "Entebbe"),
    "KGL": (-1.9686, 30.1395, "Kigali International"),
    "MPM": (-25.9208, 32.5726, "Maputo International"),
    "WDH": (-22.4799, 17.4709, "Windhoek Hosea Kutako"),
    "GBE": (-24.5552, 25.9182, "Gaborone Sir Seretse Khama"),
    "HRE": (-17.9318, 31.0928, "Harare Robert Gabriel Mugabe"),
    "LUN": (-15.3308, 28.4526, "Lusaka Kenneth Kaunda"),
    "BLZ": (-15.6791, 34.9740, "Blantyre Chileka"),
    "TNR": (-18.7969, 47.4788, "Antananarivo Ivato"),
    "MRU": (-20.4302, 57.6836, "Mauritius Sir Seewoosagur Ramgoolam"),
    "SEZ": (-4.6744, 55.5218, "Seychelles International"),
    "RUN": (-20.8871, 55.5103, "Reunion Roland Garros"),
    "FNA": (8.6164, -13.1959, "Freetown Lungi"),
    "ROB": (6.2338, -10.3623, "Monrovia Roberts"),
    "OUA": (12.3532, -1.5124, "Ouagadougou"),
    "NIM": (13.4815, 2.1834, "Niamey Diori Hamani"),
    "NDJ": (12.1337, 15.0340, "N'Djamena Hassan Djamous"),
    "BGF": (4.3985, 18.5189, "Bangui M'Poko"),
    "FIH": (-4.3858, 15.4446, "Kinshasa N'djili"),
    "BZV": (-4.2517, 15.2530, "Brazzaville Maya-Maya"),
    "LBV": (0.4584, 9.4123, "Libreville Leon M'ba"),
    "DLA": (4.0061, 9.7194, "Douala International"),
    "SSG": (3.7553, 8.7087, "Malabo"),
    "LFW": (6.1656, 1.2546, "Lome Gnassingbe Eyadema"),
    "COO": (6.3573, 2.3844, "Cotonou Cadjehoun"),
    "ABV": (9.0065, 7.2632, "Abuja Nnamdi Azikiwe"),
    "PHC": (5.0155, 6.9496, "Port Harcourt"),
    "KAN": (12.0476, 8.5246, "Kano Mallam Aminu"),
    "POS": (10.5954, -61.3372, "Port of Spain Piarco"),
    "BGI": (13.0746, -59.4925, "Barbados Grantley Adams"),
    "SXM": (18.0410, -63.1089, "Sint Maarten Princess Juliana"),
    "MBJ": (18.5037, -77.9134, "Montego Bay Sangster"),
    "KIN": (17.9356, -76.7875, "Kingston Norman Manley"),
    "NAS": (25.0390, -77.4662, "Nassau Lynden Pindling"),
    "SDQ": (18.4297, -69.6689, "Santo Domingo Las Americas"),
    "PUJ": (18.5674, -68.3634, "Punta Cana International"),
    "SJU": (18.4394, -66.0018, "San Juan Luis Munoz Marin"),
    "AUA": (12.5014, -70.0152, "Aruba Queen Beatrix"),
    "CUR": (12.1889, -68.9598, "Curacao Hato"),
    "BON": (12.1310, -68.2685, "Bonaire Flamingo"),
    "GUA": (14.5833, -90.5275, "Guatemala City La Aurora"),
    "SAL": (13.4409, -89.0557, "San Salvador Oscar Romero"),
    "TGU": (14.0610, -87.2172, "Tegucigalpa Toncontin"),
    "MGA": (12.1415, -86.1682, "Managua Augusto C. Sandino"),
    "BZE": (17.5391, -88.3082, "Belize City Philip Goldson"),
    "GDL": (20.5218, -103.3111, "Guadalajara Miguel Hidalgo"),
    "MTY": (25.7785, -100.1069, "Monterrey General Mariano Escobedo"),
    "TIJ": (32.5411, -116.9700, "Tijuana General Abelardo Rodriguez"),
    "SJD": (23.1518, -109.7215, "San Jose del Cabo International"),
    "MDE": (6.1645, -75.4231, "Medellin Jose Maria Cordova"),
    "CLO": (3.5432, -76.3816, "Cali Alfonso Bonilla Aragon"),
    "CTG": (10.4424, -75.5130, "Cartagena Rafael Nunez"),
    "UIO": (-0.1292, -78.3575, "Quito Mariscal Sucre"),
    "GYE": (-2.1574, -79.8837, "Guayaquil Jose Joaquin de Olmedo"),
    "CCS": (10.6012, -66.9913, "Caracas Simon Bolivar"),
    "LPB": (-16.5133, -68.1923, "La Paz El Alto"),
    "VVI": (-17.6448, -63.1354, "Santa Cruz Viru Viru"),
    "ASU": (-25.2400, -57.5190, "Asuncion Silvio Pettirossi"),
    "MVD": (-34.8384, -56.0308, "Montevideo Carrasco"),
    "CNF": (-19.6244, -43.9719, "Belo Horizonte Confins"),
    "BSB": (-15.8711, -47.9186, "Brasilia Presidente Juscelino"),
    "SSA": (-12.9086, -38.3225, "Salvador Deputado Luis Eduardo"),
    "REC": (-8.1264, -34.9236, "Recife Guararapes"),
    "FOR": (-3.7763, -38.5326, "Fortaleza Pinto Martins"),
    "CWB": (-25.5285, -49.1758, "Curitiba Afonso Pena"),
    "POA": (-29.9944, -51.1714, "Porto Alegre Salgado Filho"),
    "FLN": (-27.6703, -48.5525, "Florianopolis Hercilio Luz"),
    "ADL": (-34.9450, 138.5311, "Adelaide"),
    "CBR": (-35.3069, 149.1951, "Canberra"),
    "OOL": (-28.1644, 153.5047, "Gold Coast Coolangatta"),
    "CNS": (-16.8858, 145.7553, "Cairns"),
    "CHC": (-43.4894, 172.5322, "Christchurch"),
    "ZQN": (-45.0211, 168.7392, "Queenstown"),
    "PPT": (-17.5537, -149.6064, "Papeete Faa'a"),
    "NAN": (-17.7554, 177.4431, "Nadi International"),
    "SUV": (-18.0434, 178.5593, "Suva Nausori"),
    "APW": (-13.8297, -171.9978, "Apia Faleolo"),
    "TBU": (-21.2412, -175.1499, "Tongatapu Fua'amotu"),
    "HIR": (-9.4280, 160.0549, "Honiara Henderson"),
    "VLI": (-17.6993, 168.3199, "Port Vila Bauerfield"),
    "NOU": (-22.0146, 166.2128, "Noumea La Tontouta"),
    "POM": (-6.0815, 147.0100, "Port Moresby Jacksons"),
    "DIL": (-8.5464, 125.5247, "Dili Presidente Nicolau Lobato"),
    "BWN": (4.9442, 114.9283, "Brunei International"),
    "PEN": (5.2972, 100.2768, "Penang International"),
    "LGK": (6.3297, 99.7287, "Langkawi International"),
    "KBR": (6.1669, 102.2931, "Kota Bharu Sultan Ismail Petra"),
    "SBW": (2.2616, 111.9853, "Sibu"),
    "BKI": (5.9372, 116.0515, "Kota Kinabalu International"),
    "KCH": (1.4847, 110.3472, "Kuching International"),
    "CEB": (10.3076, 123.9794, "Cebu Mactan"),
    "DVO": (7.1255, 125.6456, "Davao Francisco Bangoy"),
    "ILO": (10.7133, 122.5454, "Iloilo International"),
    "CRK": (15.1860, 120.5603, "Clark International"),
    "REP": (13.4107, 107.8615, "Siem Reap Angkor"),
    "DAD": (16.0439, 108.1992, "Da Nang International"),
    "CXR": (11.9981, 109.2194, "Nha Trang Cam Ranh"),
    "PQC": (10.1698, 103.9931, "Phu Quoc International"),
    "CNX": (18.7668, 98.9626, "Chiang Mai International"),
    "HKT": (8.1132, 98.3169, "Phuket International"),
    "USM": (9.5478, 100.0623, "Koh Samui"),
    "HDY": (6.9332, 100.3930, "Hat Yai International"),
    "DMK": (13.9126, 100.6068, "Bangkok Don Mueang"),
    "RGN": (16.9073, 96.1332, "Yangon International"),
    "MDL": (21.7022, 95.9779, "Mandalay International"),
    "CCU": (22.6520, 88.4467, "Kolkata Netaji Subhas Chandra Bose"),
    "MAA": (12.9941, 80.1709, "Chennai International"),
    "BLR": (13.1979, 77.7063, "Bengaluru Kempegowda"),
    "HYD": (17.2403, 78.4294, "Hyderabad Rajiv Gandhi"),
    "COK": (10.1520, 76.4019, "Kochi International"),
    "GOI": (15.3808, 73.8314, "Goa Dabolim"),
    "AMD": (23.0772, 72.6347, "Ahmedabad Sardar Vallabhbhai Patel"),
    "JAI": (26.8242, 75.8122, "Jaipur International"),
    "IXC": (30.6735, 76.7885, "Chandigarh International"),
    "ATQ": (31.7096, 74.7973, "Amritsar Sri Guru Ram Dass Jee"),
    "TRV": (8.4821, 76.9201, "Thiruvananthapuram International"),
    "GAU": (26.1061, 91.5859, "Guwahati Lokpriya Gopinath Bordoloi"),
    "IXB": (26.6812, 88.3286, "Bagdogra"),
    "SXR": (33.9871, 74.7742, "Srinagar Sheikh ul-Alam"),
    "VNS": (25.4524, 82.8593, "Varanasi Lal Bahadur Shastri"),
    "PAT": (25.5913, 85.0880, "Patna Jay Prakash Narayan"),
    "IXR": (23.3143, 85.3217, "Ranchi Birsa Munda"),
    "RPR": (21.1804, 81.7387, "Raipur Swami Vivekananda"),
    "IDR": (22.7217, 75.8011, "Indore Devi Ahilyabai Holkar"),
    "NAG": (21.0922, 79.0472, "Nagpur Dr. Babasaheb Ambedkar"),
    "PNQ": (18.5822, 73.9197, "Pune Lohegaon"),
    "BBI": (20.2444, 85.8178, "Bhubaneswar Biju Patnaik"),
    "VTZ": (17.7212, 83.2245, "Visakhapatnam"),
    "CJB": (11.0300, 77.0434, "Coimbatore"),
    "IXM": (9.8341, 78.0934, "Madurai"),
    "TRZ": (10.7654, 78.7098, "Tiruchirappalli"),
    "PER": (-31.9403, 115.9672, "Perth"),
    "CKG": (29.7192, 106.6417, "Chongqing Jiangbei"),
    "WUH": (30.7838, 114.2081, "Wuhan Tianhe"),
    "NKG": (31.7420, 118.8620, "Nanjing Lukou"),
    "HGH": (30.2295, 120.4344, "Hangzhou Xiaoshan"),
    "XMN": (24.5440, 118.1277, "Xiamen Gaoqi"),
    "FOC": (25.9348, 119.6634, "Fuzhou Changle"),
    "TAO": (36.2661, 120.3744, "Qingdao Jiaodong"),
    "DLC": (38.9657, 121.5386, "Dalian Zhoushuizi"),
    "SHE": (41.6398, 123.4834, "Shenyang Taoxian"),
    "CGO": (34.5197, 113.8409, "Zhengzhou Xinzheng"),
    "CSX": (28.1892, 113.2200, "Changsha Huanghua"),
    "KMG": (24.9924, 102.7432, "Kunming Changshui"),
    "URC": (43.9071, 87.4742, "Urumqi Diwopu"),
    "LXA": (29.2978, 90.9119, "Lhasa Gonggar"),
    "XIY": (34.4471, 108.7516, "Xi'an Xianyang"),
    "INC": (38.3229, 106.3927, "Yinchuan Hedong"),
    "LHW": (36.5152, 103.6204, "Lanzhou Zhongchuan"),
    "KWE": (26.5385, 106.8008, "Guiyang Longdongbao"),
    "NNG": (22.6083, 108.1722, "Nanning Wuxu"),
    "HAK": (19.9349, 110.4590, "Haikou Meilan"),
    "SYX": (18.3029, 109.4122, "Sanya Phoenix"),
    "JJN": (24.7964, 118.5902, "Quanzhou Jinjiang"),
    "WNZ": (27.9122, 120.8522, "Wenzhou Longwan"),
    "TSN": (39.1244, 117.3464, "Tianjin Binhai"),
    "SJW": (38.2807, 114.6973, "Shijiazhuang Zhengding"),
    "TNA": (36.8572, 117.2156, "Jinan Yaoqiang"),
    "HFE": (31.7800, 117.2984, "Hefei Xinqiao"),
    "KHN": (28.8650, 115.9002, "Nanchang Changbei"),
    "GMP": (37.5583, 126.7906, "Seoul Gimpo"),
    "PUS": (35.1796, 128.9382, "Busan Gimhae"),
    "CJU": (33.5113, 126.4929, "Jeju International"),
    "TAE": (35.8941, 128.6589, "Daegu International"),
    "OKA": (26.1958, 127.6459, "Okinawa Naha"),
    "FUK": (33.5859, 130.4511, "Fukuoka"),
    "CTS": (42.7752, 141.6925, "Sapporo New Chitose"),
    "SDJ": (38.1397, 140.9170, "Sendai"),
    "ITM": (34.7855, 135.4380, "Osaka Itami"),
    "HIJ": (34.4361, 132.9194, "Hiroshima"),
    "MYJ": (33.8272, 132.6997, "Matsuyama"),
    "OKJ": (34.7569, 133.8551, "Okayama Momotaro"),
    "UBN": (47.6469, 106.8221, "Ulaanbaatar Chinggis Khaan New"),
    "VVO": (43.3960, 132.1483, "Vladivostok"),
    "KHV": (48.5280, 135.1884, "Khabarovsk Novy"),
    "IKT": (52.2680, 104.3886, "Irkutsk"),
    "OVB": (55.0126, 82.6507, "Novosibirsk Tolmachevo"),
    "SVX": (56.7431, 60.8027, "Yekaterinburg Koltsovo"),
    "KZN": (55.6062, 49.2787, "Kazan International"),
    "ROV": (47.4936, 39.9244, "Rostov-on-Don Platov"),
    "AER": (43.4500, 39.9566, "Sochi International"),
    "KRR": (45.0347, 39.1705, "Krasnodar Pashkovsky"),
    "MRV": (44.2251, 43.0819, "Mineralnye Vody"),
}


class OptimizeRequest(BaseModel):
    origin: str
    destination: str
    aircraft: str = "A320"
    departure_iso: str = "2025-01-15T10:00:00Z"
    weights: Dict[str, float] = {"co2": 0.4, "contrail": 0.4, "time": 0.2}
    use_noaa: bool = True


def geocode_location(query: str) -> dict:
    """Resolve IATA code or city name to coordinates."""
    q = query.strip().upper()
    
    # Check airport database
    if q in AIRPORTS:
        lat, lon, name = AIRPORTS[q]
        return {"lat": lat, "lon": lon, "name": name, "code": q}
    
    # Search by partial name
    q_lower = query.strip().lower()
    for code, (lat, lon, name) in AIRPORTS.items():
        if q_lower in name.lower():
            return {"lat": lat, "lon": lon, "name": name, "code": code}
    
    # Try geopy as fallback
    try:
        from geopy.geocoders import Nominatim
        geolocator = Nominatim(user_agent="greenpath")
        location = geolocator.geocode(query)
        if location:
            return {"lat": location.latitude, "lon": location.longitude, "name": location.address, "code": ""}
    except Exception:
        pass
    
    return None


@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0.0", "engine": "NSGA-II"}


@app.get("/geocode")
async def geocode(q: str = Query(..., description="IATA code or city name")):
    result = geocode_location(q)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Location not found: {q}")
    return result


@app.get("/airports")
async def list_airports(q: str = Query("", description="Search filter")):
    """Search airports by code or name."""
    q_lower = q.strip().lower()
    results = []
    for code, (lat, lon, name) in AIRPORTS.items():
        if not q_lower or q_lower in code.lower() or q_lower in name.lower():
            results.append({"code": code, "name": name, "lat": lat, "lon": lon})
        if len(results) >= 20:
            break
    return results


@app.post("/optimize")
async def optimize(req: OptimizeRequest):
    """Run NSGA-II flight path optimization."""
    total_start = _time.time()
    logger.info("="*60)
    logger.info(f"[OPTIMIZE] New request: {req.origin} → {req.destination}")
    logger.info(f"[OPTIMIZE] Aircraft: {req.aircraft}, NOAA: {req.use_noaa}")
    logger.info(f"[OPTIMIZE] Weights: CO₂={req.weights.get('co2',0):.2f} Contrail={req.weights.get('contrail',0):.2f} Time={req.weights.get('time',0):.2f}")

    # Validate aircraft
    if req.aircraft not in AIRCRAFT:
        raise HTTPException(status_code=400, detail=f"Unknown aircraft: {req.aircraft}. Valid: {list(AIRCRAFT.keys())}")
    
    # Geocode origin and destination
    origin = geocode_location(req.origin)
    if origin is None:
        raise HTTPException(status_code=404, detail=f"Origin not found: {req.origin}")
    logger.info(f"[OPTIMIZE] Origin: {origin['code']} ({origin['lat']:.2f}, {origin['lon']:.2f}) — {origin['name']}")
    
    dest = geocode_location(req.destination)
    if dest is None:
        raise HTTPException(status_code=404, detail=f"Destination not found: {req.destination}")
    logger.info(f"[OPTIMIZE] Dest: {dest['code']} ({dest['lat']:.2f}, {dest['lon']:.2f}) — {dest['name']}")
    
    route_dist = haversine_distance_km(origin['lat'], origin['lon'], dest['lat'], dest['lon'])
    logger.info(f"[OPTIMIZE] Great circle distance: {route_dist:.0f} km")

    # Parse departure time
    try:
        dep_time = datetime.fromisoformat(req.departure_iso.replace("Z", "+00:00"))
    except ValueError:
        dep_time = datetime(2025, 1, 15, 10, 0, 0)
    
    dep_hour = dep_time.hour + dep_time.minute / 60.0
    
    # Fetch atmospheric data
    atmo_start = _time.time()
    atmo_data = fetch_gfs_data(
        origin["lat"], origin["lon"],
        dest["lat"], dest["lon"],
        dep_time,
        use_noaa=req.use_noaa
    )
    atmo_elapsed = _time.time() - atmo_start
    
    gfs_source = str(atmo_data.get("source", ["synthetic_fallback"])[0])
    gfs_timestamp = str(atmo_data.get("timestamp", [dep_time.isoformat()])[0])
    logger.info(f"[OPTIMIZE] Atmosphere source: {gfs_source} (fetched in {atmo_elapsed:.1f}s)")
    
    # Run NSGA-II
    nsga_start = _time.time()
    logger.info(f"[OPTIMIZE] Starting NSGA-II (pop=100, gen=80)...")
    result = run_nsga2(
        origin=(origin["lat"], origin["lon"]),
        destination=(dest["lat"], dest["lon"]),
        aircraft_type=req.aircraft,
        atmo_data=atmo_data,
        departure_hour=dep_hour,
        pop_size=100,
        n_generations=80,
    )
    nsga_elapsed = _time.time() - nsga_start
    logger.info(f"[OPTIMIZE] NSGA-II completed in {nsga_elapsed:.1f}s — {len(result['pareto_front'])} Pareto solutions")
    
    # Select best solution based on weights
    selected = select_by_weights(result["pareto_front"], req.weights)
    
    if selected is None:
        raise HTTPException(status_code=500, detail="Optimization failed to produce results")
    
    # Compute baseline for comparison
    gc_points = great_circle_waypoints(origin["lat"], origin["lon"], dest["lat"], dest["lon"], 20)
    baseline_waypoints = [(lat, lon, 2) for lat, lon in gc_points]
    baseline_co2 = f1_co2(baseline_waypoints, req.aircraft, atmo_data)
    baseline_ef = f2_contrail_ef(baseline_waypoints, atmo_data, dep_hour)
    baseline_time = f3_time(baseline_waypoints, req.aircraft, atmo_data)
    
    baseline_distance = sum(
        haversine_distance_km(gc_points[i][0], gc_points[i][1], gc_points[i + 1][0], gc_points[i + 1][1])
        for i in range(len(gc_points) - 1)
    )
    
    # Compute selected path distance
    selected_wps = selected["waypoints"]
    selected_distance = sum(
        haversine_distance_km(selected_wps[i][0], selected_wps[i][1], selected_wps[i + 1][0], selected_wps[i + 1][1])
        for i in range(len(selected_wps) - 1)
    )
    
    # Stats
    co2_saving_pct = ((baseline_co2 - selected["co2_kg"]) / baseline_co2 * 100) if baseline_co2 > 0 else 0
    ef_reduction_pct = ((baseline_ef - selected["contrail_ef"]) / baseline_ef * 100) if baseline_ef > 0 else 0
    extra_km = selected_distance - baseline_distance
    extra_min = selected["time_min"] - baseline_time

    logger.info(f"[OPTIMIZE] Baseline: CO₂={baseline_co2:.0f}kg EF={baseline_ef:.1f} Time={baseline_time:.0f}min")
    logger.info(f"[OPTIMIZE] Selected: CO₂={selected['co2_kg']:.0f}kg EF={selected['contrail_ef']:.1f} Time={selected['time_min']:.0f}min")
    logger.info(f"[OPTIMIZE] Savings: CO₂={co2_saving_pct:.1f}% EF={ef_reduction_pct:.1f}% Extra={extra_km:.0f}km/{extra_min:.0f}min")
    
    # Interpolate selected path for smooth rendering
    interpolated = interpolate_path(selected_wps, points_per_segment=5)
    
    # Build selected path with ISSR data
    selected_path = []
    for lat, lon, alt in interpolated:
        issr = get_issr_at_point(lat, lon, alt, atmo_data)
        pressure = altitude_band_to_pressure(alt)
        temp_at_point = 216.65
        contrail_info = check_contrail_formation(temp_at_point, 60.0, pressure, AIRCRAFT[req.aircraft]["eta"])
        
        selected_path.append({
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "alt_ft": altitude_band_to_ft(alt),
            "issr_intensity": round(issr, 2),
            "contrail_risk": "high" if issr > 10 else "medium" if issr > 3 else "low",
        })
    
    # Build baseline path
    baseline_path = [{"lat": round(lat, 4), "lon": round(lon, 4)} for lat, lon in gc_points]
    
    # Build Pareto front for visualization — include interpolated paths for client-side selection
    pareto_data = []
    for p in result["pareto_front"]:
        # Interpolate each Pareto solution path
        p_interpolated = interpolate_path(p["waypoints"], points_per_segment=5)
        p_path = []
        for lat, lon, alt in p_interpolated:
            issr = get_issr_at_point(lat, lon, alt, atmo_data)
            p_path.append({
                "lat": round(lat, 4),
                "lon": round(lon, 4),
                "alt_ft": altitude_band_to_ft(alt),
                "issr_intensity": round(issr, 2),
                "contrail_risk": "high" if issr > 10 else "medium" if issr > 3 else "low",
            })
        pareto_data.append({
            "co2_kg": round(p["co2_kg"], 1),
            "contrail_ef": round(p["contrail_ef"], 2),
            "time_min": round(p["time_min"], 1),
            "path_id": p["path_id"],
            "path": p_path,
        })
    
    # Atmosphere sample for heatmap
    atmo_sample = generate_atmosphere_sample(atmo_data, 200)

    total_elapsed = _time.time() - total_start
    logger.info(f"[OPTIMIZE] Total request time: {total_elapsed:.1f}s")
    logger.info("="*60)
    
    return {
        "selected_path": selected_path,
        "baseline_path": baseline_path,
        "pareto_front": pareto_data,
        "stats": {
            "co2_saving_pct": round(co2_saving_pct, 1),
            "ef_reduction_pct": round(ef_reduction_pct, 1),
            "extra_km": round(extra_km, 1),
            "extra_min": round(extra_min, 1),
            "baseline_co2_kg": round(baseline_co2, 1),
            "selected_co2_kg": round(selected["co2_kg"], 1),
            "baseline_ef": round(baseline_ef, 2),
            "selected_ef": round(selected["contrail_ef"], 2),
            "baseline_time_min": round(baseline_time, 1),
            "selected_time_min": round(selected["time_min"], 1),
        },
        "atmosphere_sample": atmo_sample,
        "gfs_timestamp": gfs_timestamp,
        "gfs_source": gfs_source,
        "origin": origin,
        "destination": dest,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
