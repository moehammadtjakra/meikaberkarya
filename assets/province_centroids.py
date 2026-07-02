# -*- coding: utf-8 -*-
"""
province_centroids.py
=====================
Titik pusat (lat, lon) tiap provinsi Indonesia (38 provinsi, termasuk
pemekaran Papua). Dipakai oleh geography_engine untuk bubble/scatter map
yang berjalan PENUH OFFLINE (tanpa tile internet, tanpa file geojson besar).

Jika nanti file 'assets/indonesia-provinces.geojson' disediakan, geography
engine otomatis memakai choropleth; jika tidak, memakai bubble map ini.
"""

PROVINCE_CENTROIDS = {
    "Aceh": (4.695135, 96.749397),
    "Sumatera Utara": (2.115354, 99.545097),
    "Sumatera Barat": (-0.739940, 100.800003),
    "Riau": (0.293347, 101.706825),
    "Kepulauan Riau": (3.945651, 108.142868),
    "Jambi": (-1.485183, 102.438058),
    "Sumatera Selatan": (-3.319437, 103.914398),
    "Kepulauan Bangka Belitung": (-2.741051, 106.440582),
    "Bengkulu": (-3.792845, 102.260765),
    "Lampung": (-4.558585, 105.406807),
    "Banten": (-6.405817, 106.064018),
    "DKI Jakarta": (-6.211544, 106.845172),
    "Jawa Barat": (-6.914864, 107.609810),
    "Jawa Tengah": (-7.150975, 110.140259),
    "Daerah Istimewa Yogyakarta": (-7.875389, 110.426208),
    "Jawa Timur": (-7.536064, 112.238402),
    "Bali": (-8.409518, 115.188919),
    "Nusa Tenggara Barat": (-8.652933, 117.361648),
    "Nusa Tenggara Timur": (-8.657382, 121.079369),
    "Kalimantan Barat": (-0.278781, 111.475285),
    "Kalimantan Tengah": (-1.681488, 113.382355),
    "Kalimantan Selatan": (-3.092642, 115.283758),
    "Kalimantan Timur": (0.538659, 116.419389),
    "Kalimantan Utara": (3.073000, 116.041000),
    "Sulawesi Utara": (0.624693, 123.975002),
    "Gorontalo": (0.699944, 122.446724),
    "Sulawesi Tengah": (-1.430025, 121.445618),
    "Sulawesi Barat": (-2.844137, 119.232078),
    "Sulawesi Selatan": (-3.668800, 119.974053),
    "Sulawesi Tenggara": (-4.144910, 122.174605),
    "Maluku": (-3.238462, 130.145273),
    "Maluku Utara": (1.570999, 127.808769),
    "Papua Barat": (-1.336115, 133.174716),
    "Papua Barat Daya": (-1.000000, 131.300000),
    "Papua": (-4.269928, 138.080353),
    "Papua Tengah": (-3.500000, 136.500000),
    "Papua Pegunungan": (-4.000000, 138.900000),
    "Papua Selatan": (-7.000000, 139.500000),
}
