import json
from flask import Flask, request, jsonify, render_template, redirect, url_for, session
from modules.car_recommender import CarRecommendationSystem
from modules.utils import convert_numpy_types, NumpyEncoder
import os
import stripe
import uuid
from dotenv import load_dotenv
from datetime import datetime
from flask_mail import Mail, Message

load_dotenv()

# Create Flask application
app = Flask(__name__)
# Flask-Mail SMTP configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USER')  # Gmail email
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASS')  # App password
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_USER')

mail = Mail(app)

# Secret key for session management
app.secret_key = os.urandom(24)

# Apply the custom JSON encoder
app.json_encoder = NumpyEncoder

# Configure Stripe with your secret key from .env file
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY')
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

@app.route('/confirm_booking/<car_id>', methods=['GET'])
def confirm_booking(car_id):
    """Show booking confirmation page for selected car."""
    try:
        car_id = int(car_id)
    except ValueError:
        return jsonify({"error": "Invalid car ID format"}), 400
    
    # Retrieve car details from recommendation system
    car_details = recommender.get_car_details(car_id)
    if not car_details:
        return jsonify({"error": "Car not found"}), 404
    
    # Get rental days from query params or default to 1
    rental_days = request.args.get('days', 1, type=int)
    
    # Calculate total cost
    total_cost = int(car_details['price_per_day']) * rental_days
    
    return render_template('confirmation.html', 
                          car=car_details,
                          days=rental_days,
                          total_cost=total_cost)

@app.route('/payment/<car_id>', methods=['GET'])
def payment_page(car_id):
    """Show the payment form page."""
    try:
        car_id = int(car_id)
    except ValueError:
        return jsonify({"error": "Invalid car ID format"}), 400
    # Retrieve car details from recommendation system
    car_details = recommender.get_car_details(car_id)
    if not car_details:
        return jsonify({"error": "Car not found"}), 404
    
    # Get rental days from query params or default to 1
    rental_days = request.args.get('days', 1, type=int)
    
    # Calculate total amount
    total_amount = int(car_details['price_per_day']) * rental_days
    
    return render_template('payment.html', 
                          car=car_details, 
                          days=rental_days,
                          amount=total_amount,
                          stripe_public_key=STRIPE_PUBLIC_KEY)

@app.route('/create_payment_intent', methods=['POST'])
def create_payment_intent():
    """Create a PaymentIntent for Stripe."""
    data = request.get_json()
    car_id = int(data.get('car_id'))
    rental_days = data.get('rental_days', 1)
    
    # Get car details
    car_details = recommender.get_car_details(car_id)
    if not car_details:
        return jsonify({"error": "Car not found"}), 404
    
    # Calculate amount (convert price per day to cents for Stripe)
    amount = int(float(car_details['price_per_day']) * rental_days * 100)
    
    # Create payment intent
    try:
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency='inr',
            metadata={
                'car_id': car_id,
                'rental_days': rental_days,
                'amount': amount
            }
        )
        
        # Store booking reference in session for success page
        booking_reference = f"BK-{str(uuid.uuid4())[:8].upper()}"
        session['booking'] = {
            'reference': booking_reference,
            'car_id': car_id,
            'rental_days': rental_days,
            'amount': amount / 100  # Convert back to rupees for display
        }
        
        return jsonify({
            'clientSecret': intent.client_secret,
            'amount': amount / 100  # Convert back to rupees for display
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/update_payment_intent', methods=['POST'])
def update_payment_intent():
    """Update a PaymentIntent with customer email."""
    data = request.get_json()
    client_secret = data.get('client_secret')
    email = data.get('email')
    
    current_time = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    
    if not client_secret or not email:
        return jsonify({"error": "Missing required parameters"}), 400
    
    # Extract the payment intent ID from the client secret
    try:
        # Client secret format is usually: pi_XXX_secret_YYY
        # We need the pi_XXX part
        payment_intent_id = client_secret.split('_secret_')[0]
        
        # Update the payment intent with the email
        intent = stripe.PaymentIntent.modify(
            payment_intent_id,
            receipt_email=email,
            metadata={'customer_email': email, 'payment_date': current_time}
        )
        
        # Update session data
        if 'booking' in session:
            session['booking']['email'] = email
        
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/process_payment', methods=['POST'])
def process_payment():
    """Process payment confirmation from client."""
    data = request.get_json()
    payment_intent_id = data.get('payment_intent_id')
    email = data.get('email')
    
    try:
        # Retrieve the payment intent to confirm it's succeeded
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        if intent.status == 'succeeded':
            # Update booking with email if provided
            if email and 'booking' in session:
                session['booking']['email'] = email
            
            # Get the car details and rental information for the email receipt
            car_id = intent.metadata.get('car_id')
            rental_days = intent.metadata.get('rental_days')
            amount = intent.amount  # Amount in cents
            
            # Send email receipt
            if email:
                try:
                    send_receipt_email(email, car_id, rental_days, amount)
                except Exception as e:
                    print(f"Failed to send email receipt: {str(e)}")
            
            return jsonify({
                'success': True,
                'redirect': url_for('payment_success')
            })
        
        else:
            return jsonify({
                'success': False,
                'error': f"Payment not completed. Status: {intent.status}"
            }), 400
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/payment_success', methods=['GET'])
def payment_success():
    """Handle successful payment."""
    booking = session.get('booking', {})
    if not booking:
        return redirect(url_for('index'))
    
    car_id = booking.get('car_id')
    car_details = recommender.get_car_details(car_id)
    
    return render_template('payment_success.html',
                          booking_reference=booking.get('reference'),
                          car=car_details,
                          days=booking.get('rental_days'),
                          amount=booking.get('amount'),
                          email=booking.get('email'))

def send_receipt_email(email, car_id, rental_days, amount):
    """Send payment receipt email to customer."""
    # Get car details
    car_details = recommender.get_car_details(int(car_id))
    car_name = car_details.get('name', 'Unknown Car')
    
    # Format amount from cents to currency
    formatted_amount = float(amount) / 100
    
    # Generate current time for receipt
    payment_date = datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
    
    sender_email=os.environ.get('EMAIL_USER')
    # Create message
    msg = Message(subject="✅ Car Rental Payment Receipt",sender=sender_email,
                  recipients=[email])
    
    msg.body = (
        f"Thank you for your payment!\n\n"
        f"🔹 Car: {car_name} (ID: {car_id})\n"
        f"🔹 Rental Duration: {rental_days} day(s)\n"
        f"🔹 Amount Paid: ₹{formatted_amount:.2f}\n"
        f"🔹 Payment Date: {payment_date}\n\n"
        f"Enjoy your ride! 🚗"
    )
    
    # Send email
    mail.send(msg)
    
    return True

if __name__ == '__main__':
    app.run(debug=True)