import streamlit as st
import pandas as pd
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point

# ==========================================
# 1. THE AUTOMATED ETL PIPELINE (BACKGROUND ENGINE)
# ==========================================
@st.cache_data
def run_spatial_etl():
    # --- EXTRACT ---
    raw_hospitals = pd.read_csv("hospitals.csv")
    raw_towers = pd.read_csv("cell_towers.csv")
    
    # --- TRANSFORM (Data Cleansing) ---
    # Automatically drop rows where field workers forgot coordinates
    clean_hospitals = raw_hospitals.dropna(subset=['latitude', 'longitude'])
    clean_towers = raw_towers.dropna(subset=['latitude', 'longitude'])
    
    # Convert standard spreadsheets into Spatial DataFrames
    hosp_geometry = [Point(xy) for xy in zip(clean_hospitals.longitude, clean_hospitals.latitude)]
    towers_geometry = [Point(xy) for xy in zip(clean_towers.longitude, clean_towers.latitude)]
    
    # Create GeoDataFrames setting global GPS Coordinate System (WGS84)
    gdf_hospitals = gpd.GeoDataFrame(clean_hospitals, geometry=hosp_geometry, crs="EPSG:4326")
    gdf_towers = gpd.GeoDataFrame(clean_towers, geometry=towers_geometry, crs="EPSG:4326")
    
    # Project to local meters projection (UTM 32N for Nigeria) to ensure accurate buffer math
    gdf_hospitals_meters = gdf_hospitals.to_crs(epsg=32632)
    gdf_towers_meters = gdf_towers.to_crs(epsg=32632)
    
    return gdf_hospitals_meters, gdf_towers_meters

# Execute the pipeline seamlessly behind the scenes
gdf_hospitals, gdf_towers = run_spatial_etl()


# ==========================================
# 2. THE DASHBOARD INTERFACE (FRONTEND)
# ==========================================
st.set_page_config(layout="wide")
st.title("🇳🇬 Abuja Telecom Infrastructure Proximity Dashboard")
st.markdown("This automated tool evaluates cell tower distributions within critical proximity thresholds.")

# Sidebar controls for users
st.sidebar.header("Spatial Constraints")
selected_hospital = st.sidebar.selectbox("Select Target Hospital Facility:", gdf_hospitals['hospital_name'].unique())
buffer_distance = st.sidebar.selectbox("Set Buffer Proximity Radius (Meters):", [50, 100, 250, 500, 1000], index=3)

# Extract selected hospital geometry data point
hospital_row = gdf_hospitals[gdf_hospitals['hospital_name'] == selected_hospital]
hospital_geom = hospital_row.geometry.iloc[0]

# --- SPATIAL MATH ON THE FLY ---
# Draw the dynamic buffer based on the dropdown selection
hospital_buffer = hospital_geom.buffer(buffer_distance)

# Create a spatial intersection query to isolate overlapping towers
towers_inside = gdf_towers[gdf_towers.geometry.intersects(hospital_buffer)]
total_found = len(towers_inside)

# Display live calculation statistics cards
col1, col2 = st.columns(2)
with col1:
    st.metric(label="Target Buffer Radius", value=f"{buffer_distance} Meters")
with col2:
    st.metric(label="Active Cell Towers Detected Inside Buffer", value=total_found, 
              delta="Critical Asset Found" if total_found > 0 else "Clear Zone")

# --- INTERACTIVE MAP GENERATION ---
st.subheader("Interactive Spatial Assessment Map")

# Re-project items back to web projection (WGS84) for map visualization mapping
m = folium.Map(location=[9.0578, 7.4716], zoom_start=13, tiles="cartodbpositron")

# Draw the calculation buffer polygon onto the map layout
buffer_wgs = gpd.GeoDataFrame(geometry=[hospital_buffer], crs="EPSG:32632").to_crs(epsg=4326)
folium.GeoJson(buffer_wgs, style_function=lambda x: {'fillColor': '#ff0000', 'color': '#ff0000', 'weight': 1, 'fillOpacity': 0.15}).add_to(m)

# Add all hospital pins
for _, row in gdf_hospitals.to_crs(epsg=4326).iterrows():
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"Hospital: {row['hospital_name']}",
        icon=folium.Icon(color="red", icon="plus-sign")
    ).add_to(m)

# Add all cell tower inventory pins
for _, row in gdf_towers.to_crs(epsg=4326).iterrows():
    # If tower is trapped inside the buffer, highlight it yellow, otherwise blue
    is_inside = row['tower_id'] in towers_inside['tower_id'].values
    color = "orange" if is_inside else "blue"
    
    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=f"Tower ID: {row['tower_id']} ({row['provider']})",
        icon=folium.Icon(color=color, icon="signal")
    ).add_to(m)

# Render live map canvas directly onto the screen layout
st_folium(m, width="100%", height=500, returned_objects=[])

if total_found > 0:
    st.success(f"ETL pipeline successfully isolated {total_found} towers inside the boundary zone.")
    st.dataframe(towers_inside.drop(columns='geometry'))
else:
    st.warning("No telecommunications infrastructure detected within selection limits.")
