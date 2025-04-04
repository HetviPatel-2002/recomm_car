import json
from flask import Flask, request, jsonify, render_template
from modules.car_recommender import CarRecommendationSystem
from modules.utils import convert_numpy_types, NumpyEncoder

# Create Flask application
app = Flask(__name__)
# Apply the custom JSON encoder
app.json_encoder = NumpyEncoder

# Initialize the recommendation system
recommender = CarRecommendationSystem()

@app.route('/')
def index():
    locations = recommender.get_valid_locations()
    return render_template('index.html', locations=locations)

@app.route('/api/locations', methods=['GET'])
def get_locations():
    """Get list of valid locations."""
    locations = recommender.get_valid_locations()
    return jsonify({"locations": locations})

@app.route('/api/car_types', methods=['GET'])
def get_car_types():
    """Get list of valid car types."""
    car_types = recommender.get_valid_car_types()
    return jsonify({"car_types": car_types})

@app.route('/api/check_user', methods=['POST'])
def check_user():
    """Check if user exists and determine recommendation method."""
    data = request.get_json()
    user_id = data.get('user_id')
    location = data.get('location')
    
    if not user_id or not location:
        return jsonify({"error": "User ID and location are required"}), 400
        
    try:
        user_exists = recommender.check_user_exists(user_id, location)
        return jsonify({
            "user_exists": user_exists,
            "location": location,
            "user_id": user_id
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/content_recommendations', methods=['POST'])
def content_recommendations():
    """Get content-based recommendations."""
    data = request.get_json()
    location = data.get('location')
    car_type = data.get('car_type')
    max_price = data.get('max_price')
    ac_required = data.get('ac_required')
    unlimited_mileage = data.get('unlimited_mileage')
    
    # Step 1: Filter by location
    location_result = recommender.filter_by_location(location)
    if 'error' in location_result:
        return jsonify(location_result), 400
        
    # Step 2: Apply preferences
    pref_result = recommender.apply_user_preferences(car_type, max_price, ac_required, unlimited_mileage)
    if 'error' in pref_result:
        return jsonify(pref_result), 400
        
    # Step 3: Compute similarity
    sim_result = recommender.compute_similarity()
    if 'error' in sim_result:
        return jsonify(sim_result), 400
        
    # Step 4: Get recommendations
    recommendations = recommender.recommend_similar_cars()
    # Convert all numpy types before jsonify
    safe_recommendations = convert_numpy_types(recommendations)
     
    return jsonify({
        "recommendations": safe_recommendations,
        "count": len(safe_recommendations)
    })

@app.route('/api/collaborative_recommendations', methods=['POST'])
def collaborative_recommendations():
    """Get collaborative filtering recommendations."""
    data = request.get_json()
    user_id = data.get('user_id')
    location = data.get('location')
    
    if not user_id or not location:
        return jsonify({"error": "User ID and location are required"}), 400
        
    recommendations = recommender.recommend_cf_cars(user_id, location)
    
    if isinstance(recommendations, dict) and 'error' in recommendations:
        return jsonify(recommendations), 400
    # Convert all numpy types before jsonify
    safe_recommendations = convert_numpy_types(recommendations)
     
    return jsonify({
        "recommendations": safe_recommendations,
        "count": len(safe_recommendations)
    })

if __name__ == '__main__':
    app.run(debug=True)