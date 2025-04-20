import streamlit as st
import folium
from folium import plugins
from streamlit_folium import folium_static
import pandas as pd
from services.travel_service import get_all_travel_coordinates, get_travel
import random
from .map_visualization_helper import (
    calculate_map_bounds,
    process_coordinates,
    create_map_layers,
    get_map_tiles
)

# Función para crear un mapa base
def create_base_map(center=[20, 0], zoom=2):
    # Crear mapa base
    m = folium.Map(location=center, zoom_start=zoom, control_scale=True)
    
    # Añadir control de capas
    folium.LayerControl().add_to(m)
    
    # Añadir plugin de búsqueda de ubicación
    plugins.Geocoder().add_to(m)
    
    # Añadir plugin de medición
    plugins.MeasureControl().add_to(m)
    
    # Añadir plugin de pantalla completa
    plugins.Fullscreen().add_to(m)
    
    return m

# Función para añadir un marcador al mapa
def add_marker(m, lat, lon, popup=None, tooltip=None, icon=None, color='blue'):
    if not icon:
        icon = folium.Icon(color=color, icon='info-sign')
    
    folium.Marker(
        location=[lat, lon],
        popup=popup,
        tooltip=tooltip,
        icon=icon
    ).add_to(m)

# Función para añadir una línea al mapa
def add_line(m, coordinates, popup=None, tooltip=None, color='blue', weight=2):
    folium.PolyLine(
        locations=coordinates,
        popup=popup,
        tooltip=tooltip,
        color=color,
        weight=weight
    ).add_to(m)

# Función para generar un color aleatorio para cada usuario
@st.cache_data
def get_user_color(user_id):
    # Lista de colores para asignar a los usuarios
    colors = [
        'red', 'blue', 'green', 'purple', 'orange', 'darkred',
        'lightred', 'beige', 'darkblue', 'darkgreen', 'cadetblue',
        'darkpurple', 'white', 'pink', 'lightblue', 'lightgreen',
        'gray', 'black', 'lightgray'
    ]
    
    # Usar un hash simple para asignar un color consistente a cada usuario
    if user_id:
        hash_value = sum(ord(c) for c in str(user_id))
        color_index = hash_value % len(colors)
        return colors[color_index]
    
    # Color por defecto si no hay ID de usuario
    return 'blue'

# Componente para mostrar un mapa con todos los viajes
def travel_map_component(center=None, zoom=None):
    # Obtener todas las coordenadas de viajes
    coordinates = get_all_travel_coordinates()
    
    # Si no hay coordenadas, mostrar un mensaje
    if not coordinates:
        st.warning("No hay viajes disponibles para mostrar.")
        return
    
    # Verificar que tenemos datos válidos
    valid_coordinates = []
    for coord in coordinates:
        try:
            # Asegurarse de que lat y lon son números
            lat = float(coord.get('lat', 0))
            lon = float(coord.get('lon', 0))
            if lat != 0 and lon != 0:  # Filtrar coordenadas no válidas
                valid_coord = coord.copy()
                valid_coord['lat'] = lat
                valid_coord['lon'] = lon
                # Asegurarse de que timestamp es una cadena para evitar problemas
                if 'timestamp' in valid_coord:
                    valid_coord['timestamp'] = str(valid_coord['timestamp'])
                valid_coordinates.append(valid_coord)
        except (ValueError, TypeError) as e:
            # Ignorar coordenadas inválidas
            print(f"Coordenada inválida ignorada: {coord}, Error: {e}")
    
    # Si no quedan coordenadas válidas después del filtrado
    if not valid_coordinates:
        st.warning("No se encontraron coordenadas válidas para mostrar.")
        return
    
    # Convertir coordenadas a DataFrame para facilitar el manejo
    df = pd.DataFrame(valid_coordinates)

# Componente para mostrar un mapa de calor de viajes
def heatmap_component():
    # Obtener todas las coordenadas de viajes
    coordinates = get_all_travel_coordinates()
    
    # Si no hay coordenadas, mostrar un mensaje
    if not coordinates:
        st.warning("No hay viajes disponibles para mostrar en el mapa de calor.")
        return
    
    # Verificar que tenemos datos válidos
    valid_coordinates = []
    for coord in coordinates:
        try:
            # Asegurarse de que lat y lon son números
            lat = float(coord.get('lat', 0))
            lon = float(coord.get('lon', 0))
            if lat != 0 and lon != 0:  # Filtrar coordenadas no válidas
                valid_coord = coord.copy()
                valid_coord['lat'] = lat
                valid_coord['lon'] = lon
                # Asegurarse de que timestamp es una cadena para evitar problemas
                if 'timestamp' in valid_coord:
                    valid_coord['timestamp'] = str(valid_coord['timestamp'])
                valid_coordinates.append(valid_coord)
        except (ValueError, TypeError) as e:
            # Ignorar coordenadas inválidas
            print(f"Coordenada inválida ignorada: {coord}, Error: {e}")
    
    # Si no quedan coordenadas válidas después del filtrado
    if not valid_coordinates:
        st.warning("No se encontraron coordenadas válidas para mostrar.")
        return
    
    # Convertir coordenadas a DataFrame para facilitar el manejo
    df = pd.DataFrame(valid_coordinates)

@st.cache_data(ttl=300)
def create_travel_map(coords_df):
    """Crea un mapa interactivo con las coordenadas de los viajes"""
    if coords_df is None or len(coords_df) == 0:
        return None
    
    try:
        # Procesar coordenadas
        valid_coords = validate_coordinates(coords_df)
        if valid_coords is None:
            return None
        
        # Calcular límites del mapa
        bounds = calculate_map_bounds(valid_coords)
        if bounds is None:
            return None
        
        # Calcular centro del mapa
        center_lat = (bounds[0][0] + bounds[1][0]) / 2
        center_lon = (bounds[0][1] + bounds[1][1]) / 2
        
        # Crear mapa base
        m = folium.Map(
            location=[center_lat, center_lon],
            zoom_start=10,
            control_scale=True
        )
        
        # Obtener capas del mapa
        layers = create_map_layers(valid_coords)
        if layers is None:
            return None
        
        # Añadir capas al mapa
        for layer in layers.values():
            layer.add_to(m)
        
        # Añadir control de capas
        folium.LayerControl().add_to(m)
        
        # Añadir plugins útiles
        folium.plugins.Fullscreen().add_to(m)
        folium.plugins.MousePosition().add_to(m)
        folium.plugins.MeasureControl().add_to(m)
        
        # Añadir selector de tiles
        tiles = get_map_tiles()
        for tile_name, tile_url in tiles.items():
            if tile_name != 'OpenStreetMap':  # OpenStreetMap ya está como base
                folium.TileLayer(
                    tiles=tile_url,
                    name=tile_name,
                    attr='Map tiles by Stamen Design'
                ).add_to(m)
        
        # Ajustar a los límites
        m.fit_bounds(bounds)
        
        return m
        
    except Exception as e:
        print(f"Error creando mapa: {e}")
        return None

@st.cache_data(ttl=300)
def validate_coordinates(coords_df):
    """Valida y procesa las coordenadas para el mapa"""
    return process_coordinates(coords_df)

@st.cache_data(ttl=300)
def generate_map_statistics(coords_df):
    """Genera estadísticas del mapa"""
    if coords_df is None or len(coords_df) == 0:
        return None
    
    try:
        stats = {
            'total_points': len(coords_df),
            'unique_travels': len(coords_df['travel_id'].unique()),
            'date_range': [
                coords_df['timestamp'].min(),
                coords_df['timestamp'].max()
            ] if 'timestamp' in coords_df.columns else None,
            'bounds': calculate_map_bounds(coords_df)
        }
        
        return stats
        
    except Exception as e:
        print(f"Error generando estadísticas: {e}")
        return None