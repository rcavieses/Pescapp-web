import streamlit as st
from components.navigation import setup_sidebar, show_header
from services.get_data_utils import (
    load_coords, load_travels, load_users, 
    filter_data_by_user, filter_by_travel_ids,
    get_collection_count
)
import pandas as pd

# Configuración de la página
st.set_page_config(
    page_title="Visualizador de Datos",
    page_icon="📍",
    layout="wide"
)

def main():
    setup_sidebar()
    show_header("📍 Visualizador de Datos", "Explora y filtra los datos de la aplicación")
    
    # Configuración de paginación
    ITEMS_PER_PAGE = 1000
    
    # Pestañas para diferentes tipos de datos
    tab_coords, tab_travels, tab_users = st.tabs(["Coordenadas", "Viajes", "Usuarios"])
    
    with tab_coords:
        st.subheader("🗺️ Coordenadas")
        
        # Obtener conteo total
        total_coords = get_collection_count("coords")
        
        # Controles de paginación
        coords_page = st.number_input("Página", min_value=1, 
                                    max_value=(total_coords // ITEMS_PER_PAGE) + 1,
                                    value=1, key="coords_page")
        
        skip = (coords_page - 1) * ITEMS_PER_PAGE
        
        # Cargar datos con paginación
        coords_df = load_coords(limit=ITEMS_PER_PAGE, skip=skip)
        
        if coords_df is not None:
            st.write(f"Mostrando registros {skip + 1} a {min(skip + ITEMS_PER_PAGE, total_coords)} de {total_coords}")
            st.dataframe(coords_df, use_container_width=True)
    
    with tab_travels:
        st.subheader("🛥️ Viajes")
        
        # Obtener conteo total
        total_travels = get_collection_count("travels")
        
        # Controles de paginación
        travels_page = st.number_input("Página", min_value=1,
                                     max_value=(total_travels // ITEMS_PER_PAGE) + 1,
                                     value=1, key="travels_page")
        
        skip = (travels_page - 1) * ITEMS_PER_PAGE
        
        # Cargar datos con paginación
        travels_df = load_travels(limit=ITEMS_PER_PAGE, skip=skip)
        
        if travels_df is not None:
            st.write(f"Mostrando registros {skip + 1} a {min(skip + ITEMS_PER_PAGE, total_travels)} de {total_travels}")
            st.dataframe(travels_df, use_container_width=True)
    
    with tab_users:
        st.subheader("👥 Usuarios")
        
        # Obtener conteo total
        total_users = get_collection_count("users")
        
        # Controles de paginación
        users_page = st.number_input("Página", min_value=1,
                                   max_value=(total_users // ITEMS_PER_PAGE) + 1,
                                   value=1, key="users_page")
        
        skip = (users_page - 1) * ITEMS_PER_PAGE
        
        # Cargar datos con paginación
        users_df = load_users(limit=ITEMS_PER_PAGE, skip=skip)
        
        if users_df is not None:
            st.write(f"Mostrando registros {skip + 1} a {min(skip + ITEMS_PER_PAGE, total_users)} de {total_users}")
            st.dataframe(users_df, use_container_width=True)
    
    # Sección de filtros
    st.divider()
    st.subheader("🔍 Filtros")
    
    # Cargar datos necesarios para filtros (usando la primera página)
    users_df = load_users(limit=ITEMS_PER_PAGE)
    travels_df = load_travels(limit=ITEMS_PER_PAGE)
    coords_df = load_coords(limit=ITEMS_PER_PAGE)
    
    if users_df is not None and travels_df is not None and coords_df is not None:
        # Filtro por usuario
        user_options = ["Todos los usuarios"] + users_df["email"].unique().tolist()
        selected_user = st.selectbox("Filtrar por usuario:", user_options)
        
        # Aplicar filtro de usuario
        filtered_users_df, filtered_travels_df, filtered_coords_df = filter_data_by_user(
            users_df, travels_df, coords_df, selected_user
        )
        
        # Filtro por viaje
        if not filtered_travels_df.empty:
            travel_options = ["Todos los viajes"] + filtered_travels_df["travel_id"].unique().tolist()
            selected_travels = st.multiselect("Filtrar por viaje:", travel_options)
            
            # Aplicar filtro de viajes
            if selected_travels:
                filtered_travels_df, filtered_coords_df = filter_by_travel_ids(
                    filtered_travels_df, filtered_coords_df, selected_travels
                )
        
        # Mostrar resultados filtrados
        st.subheader("📊 Resultados Filtrados")
        
        tab1, tab2, tab3 = st.tabs(["Usuarios Filtrados", "Viajes Filtrados", "Coordenadas Filtradas"])
        
        with tab1:
            st.dataframe(filtered_users_df, use_container_width=True)
        
        with tab2:
            st.dataframe(filtered_travels_df, use_container_width=True)
        
        with tab3:
            st.dataframe(filtered_coords_df, use_container_width=True)

if __name__ == "__main__":
    main()