import os
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict

class CarRecommendationSystem:
    def __init__(self):
        """Initialize database connection and load data."""
        self.engine = self.connect_to_db()
        self.car_df = self.fetch_data_from_db('car')
        self.rental_df = self.fetch_data_from_db('rentals')
        self.filtered_cars = None
        self.similarity_matrix = None

    def connect_to_db(self):
        """Establish connection to MySQL database using SQLAlchemy."""
        try:
            password = os.getenv("DB_PASSWORD", "")
            encoded_password = password.replace("@", "%40") if password else ""
            db_url = f"mysql+pymysql://{os.getenv('DB_USER')}:{encoded_password}@{os.getenv('DB_HOST')}/tripglide"
            return create_engine(db_url, pool_pre_ping=True)
        except SQLAlchemyError as e:
            print(f"Database connection failed: {e}")
            return None

    def fetch_data_from_db(self, table_name):
        """Retrieve data from the specified table."""
        query = f"SELECT * FROM {table_name}"
        try:
            with self.engine.connect() as connection:
                return pd.read_sql(query, connection)
        except SQLAlchemyError as e:
            print(f"Failed to fetch data from {table_name}: {e}")
            return pd.DataFrame()

    def check_user_exists(self, user_id, location):
        """Check if the user exists in the database for the given location."""
        if self.rental_df.empty:
            return False
        
        # Convert location strings to lowercase for case-insensitive comparison
        location_condition = self.rental_df['Pickup_Location'].str.lower() == location.lower()
        
        # Filter rentals for this user and location
        user_rentals = self.rental_df[(self.rental_df['UserID'] == int(user_id)) & location_condition]
        
        return not user_rentals.empty

    def get_valid_locations(self):
        """Get list of valid locations from the database."""
        if self.car_df.empty:
            return []
        return sorted(self.car_df['City'].unique().tolist())

    def get_valid_car_types(self):
        """Get list of valid car types from the database."""
        if self.car_df.empty:
            return ["SUV", "Sedan", "Hatchback", "Luxury"]
        return sorted(self.car_df['CarType'].unique().tolist())

    # Content-Based Filtering Methods
    def filter_by_location(self, user_city):
        """Filter cars based on user location."""
        valid_cities = set(self.car_df["City"].str.lower().unique())
        if user_city.lower() not in valid_cities:
            return {"error": "Invalid Pickup Location. Please enter a valid city from the database."}
        
        self.filtered_cars = self.car_df[self.car_df["City"].str.lower() == user_city.lower()]
        return {"success": True, "count": len(self.filtered_cars)}

    def apply_user_preferences(self, preferred_type=None, max_price=None, ac_required=None, unlimited_mileage=None):
        """Filter cars based on user preferences."""
        if self.filtered_cars is None or self.filtered_cars.empty:
            return {"error": "No cars available for filtering."}
            
        # Set default values if user does not enter anything
        preferred_type = preferred_type.strip() if preferred_type else "SUV"
        max_price = max_price.strip() if max_price else "1000"
        ac_required = ac_required.strip().lower() if ac_required else "yes"
        unlimited_mileage = unlimited_mileage.strip().lower() if unlimited_mileage else "yes"

        valid_types = set(self.car_df["CarType"].str.lower().unique())
        if preferred_type.lower() not in valid_types:
            return {"error": f"Invalid Car Type. Choose from {', '.join(self.get_valid_car_types())}."}
        
        try:
            max_price = float(max_price)
        except ValueError:
            return {"error": "Invalid price input. Please enter a numeric value."}

        # Get the minimum price in the dataset
        min_price = self.car_df["Price_Per_Hour"].min()

        if max_price < min_price:
            return {"error": f"No cars available under ₹{max_price}/hour. The lowest price available is ₹{min_price}/hour."}

        # Validate AC & Unlimited Mileage inputs
        if ac_required not in {"yes", "no"}:
            return {"error": "AC must be either 'Yes' or 'No'."}
        if unlimited_mileage not in {"yes", "no"}:
            return {"error": "Unlimited Mileage must be either 'Yes' or 'No'."}

        # Apply filtering
        self.filtered_cars = self.filtered_cars[
            (self.filtered_cars["CarType"].str.lower() == preferred_type.lower()) &
            (self.filtered_cars["Price_Per_Hour"] <= max_price) &
            (self.filtered_cars["AC"].str.lower() == ac_required) &
            (self.filtered_cars["Unlimited_Mileage"].str.lower() == unlimited_mileage)
        ]

        if self.filtered_cars.empty:
            return {"error": f"No cars match your preferences under ₹{max_price}/hour. Try increasing your budget."}
        
        return {"success": True, "count": len(self.filtered_cars)}

    def compute_similarity(self):
        """Compute cosine similarity between car features."""
        if self.filtered_cars is None or self.filtered_cars.empty:
            return {"error": "No cars available for computing similarity."}
            
        features = ["Make", "Model", "CarType", "Transmission", "Fuel_Policy"]

        # Ensure a copy to avoid `SettingWithCopyWarning`
        self.filtered_cars = self.filtered_cars.copy()

        # Fill missing values
        self.filtered_cars.loc[:, features] = self.filtered_cars[features].fillna("Unknown")
        self.filtered_cars["combined_features"] = self.filtered_cars[features].agg(" ".join, axis=1)

        vectorizer = TfidfVectorizer()
        feature_vectors = vectorizer.fit_transform(self.filtered_cars["combined_features"])
        self.similarity_matrix = cosine_similarity(feature_vectors)
        
        return {"success": True}

    def recommend_similar_cars(self):
        """Recommend cars similar to the highest-rated car in the filtered list, ensuring diverse makes."""
        if self.filtered_cars is None or self.filtered_cars.empty or self.similarity_matrix is None:
            return []
            
        self.filtered_cars = self.filtered_cars.reset_index(drop=True)
        selected_car_index = self.filtered_cars["Rating"].idxmax()

        if selected_car_index >= len(self.similarity_matrix):
            return []

        similarity_scores = self.similarity_matrix[selected_car_index]
        similar_car_indices = np.argsort(similarity_scores)[::-1][1:41]  # Consider top 40 cars for diversity

        # Step 1: Group cars by Make
        make_groups = {}  
        for idx in similar_car_indices:
            car = self.filtered_cars.iloc[idx]
            make = car["Make"]
            if make not in make_groups:
                make_groups[make] = []
            make_groups[make].append(car)

        recommended_cars = []
        used_makes = set()

        # Step 2: Select one car per unique Make first
        for make, cars in make_groups.items():
            if len(recommended_cars) < 5:
                recommended_cars.append(cars[0])  # Pick the first car from each make
                used_makes.add(make)

        # Step 3: If we have fewer than 5, try to add from new makes first
        remaining_cars = []
        for make, cars in make_groups.items():
            if make not in used_makes:
                for car in cars:
                    if not any(car.equals(c) for c in recommended_cars):  # Fix Series comparison issue
                        remaining_cars.append(car)

        recommended_cars.extend(remaining_cars[: 5 - len(recommended_cars)])

        # Step 4: If still fewer than 5, allow duplicates but prioritize balance
        if len(recommended_cars) < 5:
            additional_cars = []
            for cars in make_groups.values():
                for car in cars:
                    if not any(car.equals(c) for c in recommended_cars):  # Fix Series comparison issue
                        additional_cars.append(car)

            recommended_cars.extend(additional_cars[: 5 - len(recommended_cars)])
            
        car_ids = [int(car["CarID"]) for car in recommended_cars]  # Convert NumPy int64 to Python int
        return self.get_car_details(car_ids)

    # Collaborative Filtering Methods
    def create_user_car_matrix(self, selected_location):
        """Create a user-car matrix for collaborative filtering."""
        if self.rental_df.empty:
            return None
            
        valid_locations = self.rental_df["Pickup_Location"].str.lower().unique()
        
        if selected_location.lower() not in valid_locations:
            return None
        
        selected_location = next(city for city in self.rental_df["Pickup_Location"].unique() 
                               if city.lower() == selected_location.lower())
        
        filtered_data = self.rental_df[self.rental_df['Pickup_Location'] == selected_location]

        if filtered_data.empty:
            return None
            
        return filtered_data.pivot_table(index='UserID', columns='CarID', values='TravelCode', aggfunc='count').fillna(0)

    def compute_cf_similarity(self, user_car_matrix):
        """Compute item-based similarity matrix for collaborative filtering."""
        if user_car_matrix is None or user_car_matrix.empty:
            return None

        item_similarity = cosine_similarity(user_car_matrix.T)
        return pd.DataFrame(item_similarity, index=user_car_matrix.columns, columns=user_car_matrix.columns)

    def recommend_cf_cars(self, user_id, selected_location):
        """Recommend cars using collaborative filtering."""
        user_car_matrix = self.create_user_car_matrix(selected_location)
        if user_car_matrix is None:
            return {"error": "No data available for the selected location."}
            
        item_sim_df = self.compute_cf_similarity(user_car_matrix)
        if item_sim_df is None:
            return {"error": "Could not compute similarity matrix."}
            
        if int(user_id) not in user_car_matrix.index:
            return {"error": "User not found in the selected location."}

        rented_cars = user_car_matrix.loc[int(user_id)]
        rented_cars = rented_cars[rented_cars > 0].index.tolist()
        recommended_cars = []

        for car in rented_cars:
            if car in item_sim_df.columns:
                similar_cars = item_sim_df[car].sort_values(ascending=False)[1:40]
                recommended_cars.extend(similar_cars.index.tolist())

        recommended_cars = list(set(recommended_cars) - set(rented_cars))  # Remove already rented cars

        if not recommended_cars:
            return {"error": "No recommendations available based on user history."}

        # Filter recommendations from car_table
        recommended_car_details = self.car_df[self.car_df["CarID"].isin(recommended_cars)].copy()

        # Group by Agency
        agency_groups = defaultdict(list)
        for _, row in recommended_car_details.iterrows():
            agency_groups[row["Agency_Name"]].append(int(row["CarID"]))  # Convert NumPy int64 to Python int

        displayed_cars = []
        used_agencies = set()

        # Step 1: Pick one car per unique agency first (ensuring agency diversity)
        for agency, cars in agency_groups.items():
            if len(displayed_cars) < 5:
                displayed_cars.append(cars[0])  # Pick the first car of each agency
                used_agencies.add(agency)

        # Step 2: If fewer than 5, add cars from new agencies first
        remaining_cars = [car for agency, cars in agency_groups.items() if agency not in used_agencies for car in cars]
        displayed_cars.extend(remaining_cars[:5 - len(displayed_cars)])

        # Step 3: If still fewer than 5, allow duplicates but keep balance
        if len(displayed_cars) < 5:
            additional_cars = recommended_car_details[~recommended_car_details["CarID"].isin(displayed_cars)]
            additional_cars = additional_cars.sort_values("Rating", ascending=False)
            displayed_cars.extend([int(car_id) for car_id in additional_cars["CarID"].tolist()[:5 - len(displayed_cars)]])

        return self.get_car_details(displayed_cars)

    def get_car_details(self, car_id):
        """Get detailed information about a specified car or list of cars."""
        # Check if car_id is a list or a single value
        if isinstance(car_id, list):
            # Handle list of car IDs
            car_details = []
            for cid in car_id:
                car = self.car_df[self.car_df["CarID"] == cid]
                if not car.empty:
                    car = car.iloc[0]
                    car_details.append({
                        "id": int(car["CarID"]),
                        "name": f"{car['Model']}",
                        "car_type": car["CarType"],
                        "fuel_policy": car["Fuel_Policy"],
                        "transmission": car["Transmission"],
                        "price_per_hour": float(car["Price_Per_Hour"]),
                        "price_per_day": float(car["Price_Per_Hour"]) * 24,
                        "rating": float(car["Rating"]),
                        "mileage_kmpl": float(car["Mileage_kmpl"]) if not pd.isna(car["Mileage_kmpl"]) else 0,
                        "occupancy": int(car["Occupancy"]) if not pd.isna(car["Occupancy"]) else 0,
                        "ac": car["AC"],
                        "unlimited_mileage": car.get("unlimited_mileage", 0),
                        "luggage_capacity": int(car["Luggage_Capacity"]),
                        "agency_name": car["Agency_Name"],
                        "base_fare": float(car["Base_Fare"]) if not pd.isna(car["Base_Fare"]) else 0,
                        "image_url": car["Image_URL"] if not pd.isna(car["Image_URL"]) else "",
                    })
            return car_details
        else:
            # Handle single car ID
            car = self.car_df[self.car_df["CarID"] == car_id]
            if not car.empty:
                car = car.iloc[0]
                return {
                    "id": int(car["CarID"]),
                    "name": f"{car['Model']}",
                    "car_type": car["CarType"],
                    "fuel_policy": car["Fuel_Policy"],
                    "transmission": car["Transmission"],
                    "price_per_hour": float(car["Price_Per_Hour"]),
                    "price_per_day": float(car["Price_Per_Hour"]) * 24,
                    "rating": float(car["Rating"]),
                    "mileage_kmpl": float(car["Mileage_kmpl"]) if not pd.isna(car["Mileage_kmpl"]) else 0,
                    "occupancy": int(car["Occupancy"]) if not pd.isna(car["Occupancy"]) else 0,
                    "ac": car["AC"],
                    "unlimited_mileage": car.get("unlimited_mileage", 0),
                    "luggage_capacity": int(car["Luggage_Capacity"]),
                    "agency_name": car["Agency_Name"],
                    "base_fare": float(car["Base_Fare"]) if not pd.isna(car["Base_Fare"]) else 0,
                    "image_url": car["Image_URL"] if not pd.isna(car["Image_URL"]) else "",
                }
            return None