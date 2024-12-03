import numpy as np
import pandas as pd
from operator import mod
import streamlit as st
import folium
from streamlit_folium import folium_static
import pickle
from sklearn.neighbors import NearestCentroid
import googlemaps
from polyline import decode
from geopy.distance import geodesic
from datetime import datetime


page_bg_img = '''
<style>
[data-testid="stAppViewContainer"] {
    background-image: url("https://i1.pickpik.com/photos/894/310/462/yellow-taxi-new-york-new-york-taxi-taxi-preview.jpg");
    background-size: cover;
    background-repeat: no-repeat;
    background-attachment: fixed;
    background-position: bottom; /* Show the bottom of the image */
    background-blend-mode: lighten; /* Blend the image to make it lighter */
    background-color: rgba(255, 255, 255, 0.8); /* Add a white overlay with 20% transparency */
}
</style>
'''

st.markdown(page_bg_img, unsafe_allow_html = True)




st.title('Ride BigApple 🚖🍎')

st.subheader('Hail a cab from your phone!')

original_pickup_coordinates = pd.read_csv('../data/clean_data/taxi_clean_set_v3.csv', usecols = ['pickup_longitude', 'pickup_latitude'])
original_dropoff_coordinates = pd.read_csv('../data/clean_data/taxi_clean_set_v3.csv', usecols = ['dropoff_longitude', 'dropoff_latitude'])



#----- models -----------------------------------------------
# main model: fare predictor
def load_model():
  with open('../models/xgb_model.pkl', 'rb') as x:
    xgb_model = pickle.load(x)
  return xgb_model

xgb_model = load_model()


# supporting model 1: pickup clusters
def load_model():
  with open('../models/dbs_pickups.pkl', 'rb') as p:
    dbs1_model = pickle.load(p)
  return dbs1_model

dbs1_model = load_model()


# supporting model 2: dropoff clusters
def load_model():
  with open('../models/dbs_dropoffs.pkl', 'rb') as d:
    dbs2_model = pickle.load(d)
  return dbs2_model

dbs2_model = load_model()
# ----- end of models section --------------------------------

#------ connect to google maps -------------------------------
api_key = 'API_KEY_HERE'
gmaps = googlemaps.Client(key = api_key)
#-------------------------------------------------------------

#----- predictive logic: functions ---------------------------
def get_coordinates(address):
    location = gmaps.geocode(address)
    if location:
        return location[0]['geometry']['location']['lat'], location[0]['geometry']['location']['lng']
    else:
        raise ValueError(f'Address {address} is invalid. Try again')


def pickup_cluster_mapping(dbs1_model, original_pickup_coordinates):
   
    cluster_centers = []
    cluster_labels = []

    # compute the centroid of each cluster (excluding noise points)
    for cluster_id in np.unique(dbs1_model.labels_):
        
        if cluster_id != -1:
            points_in_cluster = original_pickup_coordinates[dbs1_model.labels_ == cluster_id]
            cluster_centers.append(points_in_cluster.mean(axis = 0))
            cluster_labels.append(cluster_id)

    cluster_centers = np.array(cluster_centers)
    cluster_labels = np.array(cluster_labels)

    nearest_centroid = NearestCentroid()
    nearest_centroid.fit(cluster_centers, cluster_labels)

    return nearest_centroid

def dropoff_cluster_mapping(dbs2_model, original_dropoff_coordinates):
    
    cluster_centers = []
    cluster_labels = []

    # compute the centroid of each cluster (excluding noise points)
    for cluster_id in np.unique(dbs2_model.labels_):
        
        if cluster_id != -1:
            points_in_cluster = original_dropoff_coordinates[dbs2_model.labels_ == cluster_id]
            cluster_centers.append(points_in_cluster.mean(axis = 0))
            cluster_labels.append(cluster_id)

    cluster_centers = np.array(cluster_centers)
    cluster_labels = np.array(cluster_labels)

    nearest_centroid = NearestCentroid()
    nearest_centroid.fit(cluster_centers, cluster_labels)

    return nearest_centroid


pickup_cluster_mapping_model = pickup_cluster_mapping(dbs1_model, original_pickup_coordinates)
dropoff_cluster_mapping_model = dropoff_cluster_mapping(dbs2_model, original_dropoff_coordinates)


def is_within_cluster(coordinates, cluster, cluster_mapping_model):

    predicted_cluster = cluster_mapping_model.predict([coordinates])[0]

    if predicted_cluster == cluster:
        return 1
    else:
        return 0
    
def prepare_features(pickup_address, dropoff_address, pickup_cluster_mapping_model, dropoff_cluster_mapping_model):

    # parse coordinates ------------------------------------------------------------------------------------------
    pickup_coordinates = get_coordinates(pickup_address)
    dropoff_coordinates = get_coordinates(dropoff_address)
    #-------------------------------------------------------------------------------------------------------------

    
    # determine geodesic distance --------------------------------------------------------------------------------
    geodesic_distance = geodesic(pickup_coordinates, dropoff_coordinates).kilometers

    # estimate actual ride distance
    if geodesic_distance < 10:
        estimated_distance = geodesic_distance * 1.15
    else:
        estimated_distance = geodesic_distance * 1.2
    #-------------------------------------------------------------------------------------------------------------


    
    # chronological variables-------------------------------------------------------------------------------------
    now = datetime.now()
    hour = now.hour
    day = now.weekday()
    month = now.month

    # weekend rides
    if day in [5, 6]:
        weekend_rides = 1
    else:
        weekend_rides = 0    

    # xmas holiday rides
    if month in [11, 12]:
        holiday_rides = 1
    else:
        holiday_rides = 0

    # distance_hour interaction
    if estimated_distance * hour == 0:
        distance_hour = estimated_distance
    else:
        distance_hour = estimated_distance * hour
    #------------------------------------------------------------------------------------------------------------

    
    # clusters---------------------------------------------------------------------------------------------------
    # pickup clusters
    p_0 = is_within_cluster(pickup_coordinates, cluster = 0, cluster_mapping_model = pickup_cluster_mapping_model)
    p_1 = is_within_cluster(pickup_coordinates, cluster = 1, cluster_mapping_model = pickup_cluster_mapping_model)
    p_3 = is_within_cluster(pickup_coordinates, cluster = 3, cluster_mapping_model = pickup_cluster_mapping_model)
    p_4 = is_within_cluster(pickup_coordinates, cluster = 4, cluster_mapping_model = pickup_cluster_mapping_model)

    # dropoff clusters
    d_0 = is_within_cluster(dropoff_coordinates, cluster = 0, cluster_mapping_model = dropoff_cluster_mapping_model)
    d_1 = is_within_cluster(dropoff_coordinates, cluster = 1, cluster_mapping_model = dropoff_cluster_mapping_model)
    d_2 = is_within_cluster(dropoff_coordinates, cluster = 2, cluster_mapping_model = dropoff_cluster_mapping_model)
    d_3 = is_within_cluster(dropoff_coordinates, cluster = 3, cluster_mapping_model = dropoff_cluster_mapping_model)
    #-------------------------------------------------------------------------------------------------------------
    


    # JFK and LGA rides-------------------------------------------------------------------------------------------
    if p_3 or d_2:
        JFK = 1
    else:
        JFK = 0

    if p_1 or d_1:
        LGA = 1
    else:
        LGA = 0
    #-------------------------------------------------------------------------------------------------------------



    
    # gather and organize all features----------------------------------------------------------------------------
    # feature vector
    features = {
        'p_0': p_0,
        'p_1': p_1,
        'p_3': p_3,
        'p_4': p_4,
        'd_0': d_0,
        'd_1': d_1,
        'd_2': d_2,
        'd_3': d_3,
        'estimated_distance': estimated_distance,
        'distance_hour': distance_hour,
        'JFK': JFK,
        'LGA': LGA,
        'weekend_rides': weekend_rides,
        'holiday_rides': holiday_rides
    }
    #--------------------------------------------------------------------------------------------------------------

    

    return pd.DataFrame([features]), pickup_coordinates, dropoff_coordinates
#-------------------------------------------------------------------------------------------------------------------

def get_route_from_google_maps(pickup_coordinates, dropoff_coordinates):
    '''
    Fetch route information from Google Maps Directions API.
    Args:
        pickup_coords: Tuple (latitude, longitude) for the pickup location.
        dropoff_coords: Tuple (latitude, longitude) for the dropoff location.
    Returns:
        A list of route coordinates (latitude, longitude).
    '''

    # Request directions
    directions_result = gmaps.directions(
        origin = pickup_coordinates,
        destination = dropoff_coordinates,
        mode = 'driving'
    )
    
    # Extract the route (polyline) from the response
    if directions_result:
        polyline = directions_result[0]['overview_polyline']['points']
        return decode(polyline)  # Decode polyline into (latitude, longitude) pairs
    else:
        raise ValueError('No route found between the given locations.')


def plot_route_on_map(route_coords, pickup_coordinates, dropoff_coordinates):
    '''
    Plot a route and markers for pickup/dropoff locations on a Folium map.
    Args:
        route_coords: List of route coordinates (latitude, longitude).
        pickup_coords: Tuple for the pickup location.
        dropoff_coords: Tuple for the dropoff location.
    Returns:
        Folium Map object.
    '''
    # Initialize a map centered at the pickup location
    map_route = folium.Map(location = pickup_coordinates, zoom_start = 13,  tiles = 'CartoDB positron')

    # Add route to the map
    folium.PolyLine(route_coords, color = '#003366', weight = 5, opacity = 0.8).add_to(map_route)

    # add pickup and dropoff markers / what a shock to find out folium.Icon does not support hexadecimal values
    folium.Marker(pickup_coordinates, popup = 'Pickup Location', icon = folium.Icon(color = 'green')).add_to(map_route)
    folium.Marker(dropoff_coordinates, popup = 'Dropoff Location', icon = folium.Icon(color = 'red')).add_to(map_route)

    return map_route




pickup = st.text_input('Please enter your pickup location: ')
dropoff = st.text_input('Please enter your destination: ')

if st.button('Estimate your Fare'):
  if not pickup or not dropoff:
    st.error('Please enter pickup and destination')
  else:
    try:
      model_input = prepare_features(pickup, dropoff, pickup_cluster_mapping_model, dropoff_cluster_mapping_model)
      
      fare = xgb_model.predict(model_input[0])[0]
      # get distance, convert to miles
      distance = model_input[0]['estimated_distance'][0] / 1.60934
      
      st.write('**Fantastic, your NYC cab will arrive in less than 5 mins!!**')
      st.write(f'The estimated distance for your trip is **{distance:.1f}** miles.')
      st.write(f'Your fare will be approximately: **${fare:.2f}**')
      
      
      route_coordinates = get_route_from_google_maps(model_input[1], model_input[2])
      route_map = plot_route_on_map(route_coordinates,  model_input[1], model_input[2])
      folium_static(route_map)

      #st.metric('Probability', f'{100 * round(prob, 2)}%')
    except Exception as e:
      st.error(f'Error: {e}')