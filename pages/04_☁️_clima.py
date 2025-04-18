import streamlit as st
from datetime import datetime, timedelta
import pytz
from components.auth_class import Authentication
from components.navigation import setup_sidebar, show_header, show_footer
from services.firebase_service import get_collection, set_document
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
from scipy.interpolate import CubicSpline
import math

# --- Page configuration ---
st.set_page_config(
    page_title="PescApp - Clima",
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Authentication ---
auth = Authentication()
if not auth.authenticate():
    st.stop()

setup_sidebar()
user = auth.get_current_user()

show_header(
    "☁️ Información Meteorológica",
    "Consulta datos de clima, viento y mareas para planificar tus actividades de pesca."
)

# --- API keys & URLs (using Streamlit secrets) ---
OPENWEATHER_API_KEY = st.secrets.openweather_api
NOAA_API_URL = "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
NOAA_STATIONS_URL = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations.json"

# --- Firestore helpers ---
def load_saved_locations(user_id):
    try:
        doc = get_collection("user_locations").document(user_id).get()
        return doc.to_dict().get("locations", []) if doc.exists else []
    except Exception as e:
        st.error(f"Error al cargar ubicaciones: {e}")
        return []

def save_location(user_id, name, lat, lon):
    try:
        existing = load_saved_locations(user_id)
        new_loc = {
            "name": name,
            "lat": lat,
            "lon": lon,
            "saved_at": datetime.now(pytz.timezone("America/Tijuana")).isoformat()
        }
        for i, loc in enumerate(existing):
            if loc["name"] == name:
                existing[i] = new_loc
                break
        else:
            existing.append(new_loc)
        set_document("user_locations", user_id, {"locations": existing})
        return True, "Ubicación guardada."
    except Exception as e:
        return False, f"Error al guardar ubicación: {e}"

# --- Estaciones NOAA ---
@st.cache_data(ttl=3600)  # Cache por 1 hora
def get_noaa_stations():
    """Obtiene la lista de estaciones NOAA disponibles"""
    try:
        response = requests.get(NOAA_STATIONS_URL)
        if response.status_code != 200:
            return []
        
        data = response.json()
        stations = []
        
        for station in data.get('stations', []):
            if station.get('tidal', False):  # Solo estaciones con datos de mareas
                stations.append({
                    'id': station.get('id', ''),
                    'name': station.get('name', ''),
                    'lat': station.get('lat', 0),
                    'lng': station.get('lng', 0)
                })
                
        return stations
    except Exception as e:
        st.error(f"Error al obtener estaciones NOAA: {str(e)}")
        return []

def find_nearest_station(lat, lon):
    """Encuentra la estación NOAA más cercana a las coordenadas dadas"""
    stations = get_noaa_stations()
    
    if not stations:
        # Estación predeterminada como respaldo
        return "9410170"  # San Diego, CA
    
    def haversine(lat1, lon1, lat2, lon2):
        """Calcula la distancia entre dos puntos en la Tierra"""
        R = 6371  # Radio de la Tierra en km
        
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    nearest_station = None
    min_distance = float('inf')
    
    for station in stations:
        try:
            station_lat = float(station['lat'])
            station_lng = float(station['lng'])
            distance = haversine(lat, lon, station_lat, station_lng)
            
            if distance < min_distance:
                min_distance = distance
                nearest_station = station
        except (ValueError, TypeError):
            continue
    
    if nearest_station:
        st.info(f"Usando datos de la estación NOAA más cercana: {nearest_station['name']} (a {min_distance:.1f} km)")
        return nearest_station['id']
    else:
        return "9410170"  # Estación predeterminada como respaldo

# --- Data fetchers ---
def get_current_weather(lat, lon):
    try:
        api_key = st.secrets.openweather_api.get("openweather_api")
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&appid={api_key}"
            f"&units=metric&lang=es"
        )
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        
        # Validate required fields
        if "main" not in data or "weather" not in data or "wind" not in data:
            raise ValueError("Invalid API response format")
            
        return data
    except requests.RequestException as e:
        st.error(f"Error al obtener datos del clima: {str(e)}")
        return None
    except (ValueError, KeyError) as e:
        st.error(f"Error en el formato de respuesta: {str(e)}")
        return None

def get_weather_forecast(lat, lon):
    try:
        api_key = st.secrets.openweather_api.get("openweather_api")
        url = (
            f"https://api.openweathermap.org/data/2.5/forecast"
            f"?lat={lat}&lon={lon}&appid={api_key}"
            f"&units=metric&lang=es"
        )
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Error al obtener el pronóstico: {str(e)}")
        return None
    except (ValueError, KeyError) as e:
        st.error(f"Error en el formato de respuesta del pronóstico: {str(e)}")
        return None

def get_tide_data(lat, lon):
    """Obtiene datos de mareas para la ubicación más cercana"""
    try:
        # Encontrar la estación NOAA más cercana
        station_id = find_nearest_station(lat, lon)
        
        # Definir período de tiempo (2 días)
        start = datetime.now(pytz.UTC)
        end = start + timedelta(days=2)
        
        # Construir parámetros de consulta
        params = {
            "begin_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
            "station": station_id,
            "product": "predictions",
            "datum": "MLLW",  # Mean Lower Low Water
            "time_zone": "LST",  # Local Standard Time
            "interval": "hilo",  # Solo pleamar y bajamar
            "units": "metric",
            "format": "json"
        }
        
        # Realizar la consulta a la API
        response = requests.get(NOAA_API_URL, params=params)
        
        if response.status_code != 200:
            st.warning(f"No se pudieron obtener datos de mareas para esta ubicación. Código: {response.status_code}")
            return []
            
        data = response.json()
        
        # Si no hay predicciones, intentar con datos a intervalos
        if "predictions" not in data or not data["predictions"]:
            params["interval"] = "h"  # Datos horarios
            response = requests.get(NOAA_API_URL, params=params)
            data = response.json()
        
        # Procesar los datos de mareas
        tides = []
        
        for pred in data.get("predictions", []):
            try:
                dt = int(datetime.strptime(pred["t"], "%Y-%m-%d %H:%M").timestamp())
                
                # Determinar si es pleamar o bajamar para datos hilo
                if "type" in pred:
                    tide_type = "Pleamar" if pred["type"] == "H" else "Bajamar"
                else:
                    # Para datos horarios, no tenemos el tipo directamente
                    tide_type = "Nivel"
                
                tides.append({
                    "dt": dt,
                    "type": tide_type,
                    "height": float(pred["v"])
                })
            except (ValueError, KeyError) as e:
                continue
        
        return tides
        
    except Exception as e:
        st.error(f"Error al obtener datos de mareas: {str(e)}")
        return []

# --- Display functions ---
def display_current_weather(w):
    if not w:
        st.error("No hay datos del clima disponibles")
        return
        
    try:
        cols = st.columns(3)
        temp = w["main"]["temp"]
        feels = w["main"]["feels_like"]
        humidity = w["main"]["humidity"]
        pressure = w["main"]["pressure"]
        wind = w["wind"]["speed"]
        deg = w["wind"]["deg"]
        desc = w["weather"][0]["description"].capitalize()

        def card(col, title, body):
            with col:
                st.info(f"**{title}**\n\n{body}")

        card(cols[0], f"Temperatura: {temp}°C", f"Sensación: {feels}°C")
        card(cols[1], f"Viento: {wind} m/s", f"Dirección: {deg}°")
        card(cols[2], f"Humedad: {humidity}%", f"Presión: {pressure} hPa")
        st.markdown(f"**Condición:** {desc}")
    except (KeyError, IndexError) as e:
        st.error("Error al mostrar datos del clima: formato de datos inválido")

def display_forecast_chart(forecast):
    if not forecast or "list" not in forecast:
        st.error("No hay datos de pronóstico disponibles")
        return
    
    try:
        df = pd.DataFrame([{
            "fecha": pd.to_datetime(item["dt"], unit="s"),
            "temperatura": item["main"]["temp"],
            "humedad": item["main"]["humidity"],
            "viento": item["wind"]["speed"]
        } for item in forecast["list"]])
        
        fig = px.line(df, x="fecha", y=["temperatura", "viento", "humedad"],
                    labels={"fecha": "Fecha y Hora", "value": "Valor", "variable": "Parámetro"},
                    title="Pronóstico 5 días")
        st.plotly_chart(fig, use_container_width=True)
    except (KeyError, ValueError) as e:
        st.error(f"Error al procesar datos del pronóstico: {str(e)}")

def display_tide_chart(tides):
    if not tides:
        st.warning("No hay datos de mareas disponibles para esta ubicación")
        return
        
    try:
        df = pd.DataFrame([{
            "datetime": datetime.fromtimestamp(t["dt"]),
            "altura": t["height"],
            "tipo": t["type"]
        } for t in tides])
        
        # Crear la figura
        fig = go.Figure()
        
        # Agregar puntos para marcar pleamar y bajamar
        fig.add_trace(go.Scatter(
            x=df["datetime"],
            y=df["altura"],
            mode='markers+lines',
            name='Puntos de marea',
            marker=dict(
                size=10,
                color='rgb(200, 50, 50)',
                symbol='circle'
            ),
            line=dict(
                color='rgb(0, 100, 200)',
                width=2
            ),
            text=df["tipo"],
            hovertemplate='%{text}<br>Altura: %{y:.2f}m<br>%{x}<extra></extra>'
        ))
        
        fig.update_layout(
            title="Gráfica de Mareas",
            xaxis_title="Fecha y Hora",
            yaxis_title="Altura (m)",
            hovermode='x unified',
            showlegend=True
        )
        
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error al crear gráfica de mareas: {str(e)}")

def display_tide_data(tides):
    if not tides:
        st.warning("No hay datos de mareas disponibles para esta ubicación")
        return
        
    try:
        df = pd.DataFrame([{
            "Fecha y Hora": datetime.fromtimestamp(t["dt"]).strftime("%d/%m/%Y %H:%M"),
            "Tipo": t["type"],
            "Altura (m)": round(t["height"], 2)
        } for t in tides])
        st.subheader("Tabla de Mareas")
        st.dataframe(df, use_container_width=True)
        display_tide_chart(tides)
    except Exception as e:
        st.error(f"Error al mostrar tabla de mareas: {str(e)}")

def display_wind_rose(forecast):
    if not forecast or "list" not in forecast:
        st.error("No hay datos de viento disponibles")
        return
        
    try:
        df = pd.DataFrame([{
            "deg": item["wind"]["deg"],
            "speed": item["wind"]["speed"]
        } for item in forecast["list"]])
        
        # Create wind direction bins (16 directions)
        bins = np.linspace(0, 360, 17)
        labels = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        df['direction'] = pd.cut(df['deg'], bins=bins, labels=labels, include_lowest=True)
        
        # Calculate frequency for each direction and speed
        direction_counts = df.groupby('direction')['speed'].value_counts().unstack(fill_value=0)
        
        # Create the wind rose using go.Barpolar
        fig = go.Figure()
        
        # Speed bins
        speed_bins = [0, 2, 4, 6, 8, 10, np.inf]
        speed_labels = ['0-2', '2-4', '4-6', '6-8', '8-10', '>10']
        colors = px.colors.sequential.Blues[1:]
        
        for i in range(len(speed_bins)-1):
            mask = (df['speed'] >= speed_bins[i]) & (df['speed'] < speed_bins[i+1])
            counts = df[mask].groupby('direction').size()
            
            fig.add_trace(go.Barpolar(
                r=counts.values,
                theta=counts.index,
                name=f'{speed_labels[i]} m/s',
                marker_color=colors[i],
                opacity=0.7
            ))
        
        fig.update_layout(
            title="Rosa de los Vientos",
            font_size=10,
            legend_title="Velocidad (m/s)",
            polar=dict(
                radialaxis=dict(showticklabels=True, gridcolor="lightgray"),
                angularaxis=dict(direction="clockwise", rotation=90)
            ),
            showlegend=True
        )
        
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error al crear rosa de los vientos: {str(e)}")

# --- Main ---
def main():
    user_id = user["id"]
    saved = load_saved_locations(user_id)

    st.subheader("🌍 Selecciona una ubicación")
    locations = [
        {"name": "La Paz, BCS", "lat": 24.1427, "lon": -110.3127},
        {"name": "Ensenada, BC", "lat": 31.8551, "lon": -116.6287},
        {"name": "Los Cabos, BCS", "lat": 22.8905, "lon": -109.9167},
        {"name": "Puerto Peñasco, Sonora", "lat": 31.3156, "lon": -113.5336},
        {"name": "Mazatlán, Sinaloa", "lat": 23.2494, "lon": -106.4111},
        {"name": "Puerto Vallarta, Jalisco", "lat": 20.6534, "lon": -105.2253},
        {"name": "Veracruz, Veracruz", "lat": 19.2026, "lon": -96.1342},
        {"name": "Progreso, Yucatán", "lat": 21.2811, "lon": -89.6608},
        {"name": "Cancún, Q. Roo", "lat": 21.1619, "lon": -86.8515},
        {"name": "Frontera, Tabasco", "lat": 18.0000, "lon": -93.5000},
        {"name": "Ciudad del Carmen, Campeche", "lat": 18.6340, "lon": -91.8072}
    ]
    option = st.radio("Tipo:", ["Predefinidas", "Personalizada", "Guardadas"], horizontal=True)

    if option == "Predefinidas":
        choice = st.selectbox("Ubicación:", [loc["name"] for loc in locations])
        loc = next(l for l in locations if l["name"] == choice)
        lat, lon = loc["lat"], loc["lon"]

    elif option == "Personalizada":
        lat = st.number_input("Latitud", -90.0, 90.0, 24.1427)
        lon = st.number_input("Longitud", -180.0, 180.0, -110.3127)
        name = st.text_input("Nombre (opcional)")
        if st.button("💾 Guardar ubicación"):
            if name:
                ok, msg = save_location(user_id, name, lat, lon)
                st.success(msg) if ok else st.error(msg)
            else:
                st.warning("Introduce un nombre.")

    else:  # Guardadas
        if saved:
            choice = st.selectbox("Guardadas:", [loc["name"] for loc in saved])
            loc = next(l for l in saved if l["name"] == choice)
            lat, lon = loc["lat"], loc["lon"]
        else:
            st.info("No hay ubicaciones guardadas.")
            return

    if st.button("🔄 ACTUALIZAR DATOS METEOROLÓGICOS"):
        with st.spinner("Cargando…"):
            weather = get_current_weather(lat, lon)
            forecast = get_weather_forecast(lat, lon)
            tides = get_tide_data(lat, lon)

        st.header(f"Clima para {choice if option=='Predefinidas' or option=='Guardadas' else name or 'ubicación personalizada'}")
        display_current_weather(weather)

        st.header("Pronóstico")
        display_forecast_chart(forecast)

        st.header("Mareas")
        display_tide_data(tides)

        st.header("Viento")
        display_wind_rose(forecast)

    st.divider()
    with st.expander("ℹ️ Fuentes"):
        st.markdown("""
        - **Clima**: OpenWeatherMap  
        - **Mareas**: NOAA Tides & Currents  
        """)

if __name__ == "__main__":
    main()

show_footer()