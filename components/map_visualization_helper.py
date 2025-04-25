import streamlit as st
import pandas as pd
import folium
from folium import plugins
from streamlit_folium import folium_static
from services.travel_service import get_travel_coordinates, get_coords_from_collection, get_all_travel_coordinates

@st.cache_data(ttl=300)  # Cache por 5 minutos
def calculate_map_bounds(coords_df):
    """Calcula los límites del mapa basados en las coordenadas"""
    if coords_df is None or len(coords_df) == 0:
        return None
    
    try:
        min_lat = coords_df['lat'].min()
        max_lat = coords_df['lat'].max()
        min_lon = coords_df['lon'].min()
        max_lon = coords_df['lon'].max()
        
        return [[min_lat, min_lon], [max_lat, max_lon]]
    except Exception as e:
        print(f"Error calculando límites del mapa: {e}")
        return None

@st.cache_data(ttl=300)
def process_coordinates(coords_df):
    """Procesa y valida las coordenadas para el mapa"""
    if coords_df is None or len(coords_df) == 0:
        return None
        
    try:
        # Asegurar que las columnas necesarias existen
        required_cols = ['lat', 'lon', 'travel_id', 'timestamp']
        if not all(col in coords_df.columns for col in required_cols):
            return None
            
        # Convertir coordenadas a float
        coords_df['lat'] = pd.to_numeric(coords_df['lat'], errors='coerce')
        coords_df['lon'] = pd.to_numeric(coords_df['lon'], errors='coerce')
        
        # Filtrar coordenadas válidas
        valid_coords = coords_df.dropna(subset=['lat', 'lon'])
        
        # Filtrar coordenadas dentro de rangos razonables
        valid_coords = valid_coords[
            (valid_coords['lat'] >= -90) & (valid_coords['lat'] <= 90) &
            (valid_coords['lon'] >= -180) & (valid_coords['lon'] <= 180)
        ]
        
        return valid_coords if len(valid_coords) > 0 else None
        
    except Exception as e:
        print(f"Error procesando coordenadas: {e}")
        return None

@st.cache_data(ttl=300)
def create_map_layers(valid_coords):
    """Crea las capas del mapa para diferentes tipos de visualización"""
    if valid_coords is None:
        return None
        
    try:
        layers = {
            'Puntos': folium.FeatureGroup(name='Puntos'),
            'Rutas': folium.FeatureGroup(name='Rutas'),
            'Calor': folium.FeatureGroup(name='Mapa de Calor')
        }
        
        # Añadir puntos
        for idx, row in valid_coords.iterrows():
            popup_text = f"""
                <b>Viaje:</b> {row['travel_id']}<br>
                <b>Timestamp:</b> {row['timestamp']}<br>
                <b>Coordenadas:</b> [{row['lat']:.6f}, {row['lon']:.6f}]
            """
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=6,
                popup=popup_text,
                color='blue',
                fill=True
            ).add_to(layers['Puntos'])
        
        # Añadir rutas por viaje
        for travel_id in valid_coords['travel_id'].unique():
            travel_coords = valid_coords[valid_coords['travel_id'] == travel_id]
            if len(travel_coords) > 1:
                coordinates = travel_coords[['lat', 'lon']].values.tolist()
                folium.PolyLine(
                    coordinates,
                    weight=2,
                    color='red',
                    opacity=0.8
                ).add_to(layers['Rutas'])
        
        # Añadir mapa de calor
        heat_data = valid_coords[['lat', 'lon']].values.tolist()
        if heat_data:
            folium.plugins.HeatMap(heat_data).add_to(layers['Calor'])
        
        return layers
        
    except Exception as e:
        print(f"Error creando capas del mapa: {e}")
        return None

@st.cache_data(ttl=300)
def get_map_tiles():
    """Retorna las diferentes opciones de tiles para el mapa"""
    return {
        'OpenStreetMap': 'OpenStreetMap',
        'Satélite': 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        'Terreno': 'Stamen Terrain'
    }

def show_direct_coords_map():
    """
    Muestra un mapa con coordenadas cargadas directamente de la colección 'coords'
    Útil para depurar problemas con las coordenadas
    """
    st.subheader("Mapa de Coordenadas Directas")
    
    # Cargar coordenadas directamente de la colección
    with st.spinner("Cargando coordenadas directamente de la base de datos..."):
        coords = get_coords_from_collection(limit=500)  # Limitar a 500 para rendimiento
    
    if not coords:
        st.warning("No se encontraron coordenadas en la colección 'coords'")
        return
    
    # Convertir a DataFrame
    try:
        df = pd.DataFrame(coords)
        
        # Verificar que contiene las columnas necesarias
        required_columns = ['lat', 'lon']
        if not all(col in df.columns for col in required_columns):
            st.error("Los datos no contienen las columnas requeridas (lat, lon)")
            st.write("Columnas disponibles:", df.columns.tolist())
            return
        
        # Asegurar que lat/lon son numéricos
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        # Eliminar filas con valores NaN
        df = df.dropna(subset=['lat', 'lon'])
        
        # Añadir una columna travel_id si no existe
        if 'travel_id' not in df.columns:
            df['travel_id'] = "desconocido"
        
        # Mostrar información
        st.success(f"Se cargaron {len(df)} coordenadas válidas")
        
        # Mostrar una muestra de los datos
        st.write("Muestra de los datos:")
        st.dataframe(df.head())
        
        # Crear el mapa
        create_folium_map(df)
    
    except Exception as e:
        st.error(f"Error al procesar coordenadas: {str(e)}")

@st.cache_data(ttl=300)
def process_map_data(df):
    """
    Procesa los datos para el mapa y retorna un diccionario con datos serializables
    """
    try:
        # Asegurar que lat/lon son numéricos
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        # Eliminar filas con valores NaN
        df = df.dropna(subset=['lat', 'lon'])
        
        # Preparar datos para el mapa
        map_data = {
            'coordinates': df[['lat', 'lon']].values.tolist(),
            'travel_ids': df['travel_id'].unique().tolist(),
            'center': [df['lat'].mean(), df['lon'].mean()],
            'bounds': [
                [df['lat'].min(), df['lon'].min()],
                [df['lat'].max(), df['lon'].max()]
            ]
        }
        
        # Añadir datos adicionales si están disponibles
        if 'timestamp' in df.columns:
            map_data['timestamps'] = df['timestamp'].tolist()
            
        return map_data
    except Exception as e:
        print(f"Error al procesar datos del mapa: {str(e)}")
        return None

def create_folium_map(df, width=800, height=600):
    """
    Crea y muestra un mapa de Folium con las coordenadas procesadas
    
    Args:
        df: DataFrame de pandas con columnas 'lat' y 'lon'
        width: Ancho del mapa
        height: Alto del mapa
    """
    try:
        # Procesar datos primero (esto será cacheado)
        map_data = process_map_data(df)
        if not map_data:
            return None
            
        # Crear mapa base con el centro calculado
        m = folium.Map(location=map_data['center'], zoom_start=10, control_scale=True)
        
        # Añadir controles
        folium.LayerControl().add_to(m)
        plugins.Fullscreen().add_to(m)
        plugins.MousePosition().add_to(m)
        plugins.MeasureControl().add_to(m)
        
        # Colores para diferentes viajes
        colors = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'lightblue', 
                 'darkgreen', 'cadetblue', 'darkpurple', 'beige', 'pink', 'gray']
        
        # Crear las capas del mapa usando los datos procesados
        for i, travel_id in enumerate(map_data['travel_ids']):
            color = colors[i % len(colors)]
            
            # Filtrar puntos para este viaje
            travel_points = df[df['travel_id'] == travel_id]
            point_coords = travel_points[['lat', 'lon']].values.tolist()
            
            # Añadir marcadores y líneas
            for j, point in enumerate(point_coords):
                popup_text = f"Viaje: {travel_id}"
                if 'timestamps' in map_data:
                    popup_text += f"<br>Tiempo: {map_data['timestamps'][j]}"
                
                folium.Marker(
                    location=point,
                    popup=popup_text,
                    tooltip=f"Viaje: {travel_id}",
                    icon=folium.Icon(color=color, icon='info-sign')
                ).add_to(m)
            
            # Añadir línea si hay más de un punto
            if len(point_coords) >= 2:
                folium.PolyLine(
                    locations=point_coords,
                    color=color,
                    weight=2.5,
                    opacity=0.7
                ).add_to(m)
        
        # Ajustar a los límites
        m.fit_bounds(map_data['bounds'])
        
        return m
        
    except Exception as e:
        print(f"Error al crear el mapa: {str(e)}")
        return None

def quick_map_visualization():
    """
    Función para mostrar rápidamente un mapa con todas las coordenadas disponibles
    """
    st.subheader("Visualización Rápida de Viajes")
    
    # Ofrecer opciones de origen de datos
    data_source = st.radio(
        "Origen de los datos:",
        ["Viajes disponibles (recomendado)", "Colección coords directa"],
        horizontal=True
    )
    
    with st.spinner("Cargando coordenadas..."):
        # Obtener coordenadas según la opción seleccionada
        if data_source == "Colección coords directa":
            coords = get_coords_from_collection(limit=500)
            source_text = "colección coords"
        else:
            coords = get_all_travel_coordinates()
            source_text = "viajes disponibles"
    
    if not coords:
        st.warning(f"No se encontraron coordenadas en {source_text}")
        return
    
    # Convertir a DataFrame
    try:
        df = pd.DataFrame(coords)
        
        # Verificar que contiene las columnas necesarias
        required_columns = ['lat', 'lon']
        if not all(col in df.columns for col in required_columns):
            st.error("Los datos no contienen las columnas requeridas (lat, lon)")
            st.write("Columnas disponibles:", df.columns.tolist())
            return
        
        # Asegurar que lat/lon son numéricos
        df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
        df['lon'] = pd.to_numeric(df['lon'], errors='coerce')
        
        # Eliminar filas con valores NaN
        df = df.dropna(subset=['lat', 'lon'])
        
        # Mostrar información
        st.success(f"Se cargaron {len(df)} coordenadas válidas de {source_text}")
        
        # Crear el mapa
        create_folium_map(df)
    
    except Exception as e:
        st.error(f"Error al procesar coordenadas: {str(e)}")