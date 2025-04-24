// Global variables
let currentStep = 1;
let currentUserId = null;
let currentLocation = null;
let hasRentalHistory = false;  // Renamed from isExistingUser for clarity

// DOM elements
const userForm = document.getElementById('userForm');
const preferencesForm = document.getElementById('preferencesForm');
const locationSelect = document.getElementById('location');
const carTypeSelect = document.getElementById('carType');
const recommendationsContainer = document.getElementById('recommendationsContainer');

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Load locations
    fetchLocations();
    
    // Load car types
    fetchCarTypes();
});

userForm.addEventListener('submit', function(e) {
    e.preventDefault();
    
    // Show loader and hide error message
    document.getElementById('step1Loader').style.display = 'block';
    document.getElementById('step1Error').style.display = 'none';
    
    // Get form values
    const userName = document.getElementById('userName').value.trim();
    const userEmail = document.getElementById('userEmail').value.trim();
    const location = locationSelect.value;
    
    // Validate form inputs
    if (!userName || !userEmail || !location) {
        showError('step1Error', 'Please fill in all fields');
        hideLoader('step1Loader');
        return;
    }
    
    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(userEmail)) {
        showError('step1Error', 'Please enter a valid email address');
        hideLoader('step1Loader');
        return;
    }
    
    // Check if user exists in the system
    checkUser(userName, userEmail, location);
});

preferencesForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const carType = carTypeSelect.value;
    const maxPrice = document.getElementById('maxPrice').value;
    const acRequired = document.getElementById('acRequired').checked;
    const unlimitedMileage = document.getElementById('unlimitedMileage').checked;

    if (!carType) {
        showError('step2Error', 'Please select a car type');
        return;
    }

    // Get content-based recommendations
    getContentRecommendations(currentLocation, carType, maxPrice, acRequired, unlimitedMileage);
});

// Functions
function fetchLocations() {
    showLoader('step1Loader');
    fetch('/api/locations')
        .then(response => response.json())
        .then(data => {
            hideLoader('step1Loader');
            if (data.locations && Array.isArray(data.locations)) {
                locationSelect.innerHTML = '<option value="">-- Select a location --</option>';
                data.locations.forEach(location => {
                    const option = document.createElement('option');
                    option.value = location;
                    option.textContent = location;
                    locationSelect.appendChild(option);
                });
            } else {
                showError('step1Error', 'Failed to load locations: Invalid data format');
            }
        })
        .catch(error => {
            hideLoader('step1Loader');
            showError('step1Error', 'Failed to load locations: ' + error.message);
        });
}

function fetchCarTypes() {
    fetch('/api/car_types')
        .then(response => response.json())
        .then(data => {
            if (data.car_types && Array.isArray(data.car_types)) {
                carTypeSelect.innerHTML = '<option value="">-- Select car type --</option>';
                data.car_types.forEach(type => {
                    const option = document.createElement('option');
                    option.value = type;
                    option.textContent = type;
                    carTypeSelect.appendChild(option);
                });
            } else {
                showError('step2Error', 'Failed to load car types: Invalid data format');
            }
        })
        .catch(error => {
            showError('step2Error', 'Failed to load car types: ' + error.message);
        });
}

function checkUser(userName, userEmail, location) {
    fetch('/api/check_user', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            name: userName,
            email: userEmail,
            location: location 
        }),
    })
    .then(response => response.json())
    .then(data => {
        hideLoader('step1Loader');
        if (data.error) {
            showError('step1Error', data.error);
            return;
        }
        
        currentLocation = location;
        
        // Store selected location in sessionStorage
        sessionStorage.setItem('selectedLocation', location);
        
        if (data.user_exists) {
            // User exists and has rental history - get collaborative recommendations
            currentUserId = data.user_id;
            hasRentalHistory = true;
            sessionStorage.setItem('userId', data.user_id);
            
            getCollaborativeRecommendations(currentUserId, location);
        } else {
            // User doesn't exist or has no rental history - go to preferences form
            if (data.user_id) {
                // User exists but no rental history
                currentUserId = data.user_id;
                sessionStorage.setItem('userId', data.user_id);
            }
            hasRentalHistory = false;
            goToStep(2);
        }
    })
    .catch(error => {
        hideLoader('step1Loader');
        showError('step1Error', 'Error checking user: ' + error.message);
    });
}

function getContentRecommendations(location, carType, maxPrice, acRequired, unlimitedMileage) {
    showLoader('step2Loader');
    fetch('/api/content_recommendations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            location: location,
            car_type: carType,
            max_price: maxPrice,
            ac_required: acRequired,
            unlimited_mileage: unlimitedMileage,
            user_id: currentUserId // Send user_id if available
        }),
    })
    .then(response => response.json())
    .then(data => {
        hideLoader('step2Loader');
        if (data.error) {
            showError('step2Error', data.error);
            return;
        }
        
        displayRecommendations(data.recommendations);
        goToStep(3);
    })
    .catch(error => {
        hideLoader('step2Loader');
        showError('step2Error', 'Error getting recommendations: ' + error.message);
    });
}

function getCollaborativeRecommendations(userId, location) {
    showLoader('step1Loader');
    fetch('/api/collaborative_recommendations', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            user_id: userId,
            location: location
        }),
    })
    .then(response => response.json())
    .then(data => {
        hideLoader('step1Loader');
        
        if (data.error) {
            // If collaborative filtering fails, fall back to preferences-based approach
            showError('step1Error', `${data.error}. We'll find cars based on your preferences instead.`);
            setTimeout(() => {
                goToStep(2);
            }, 2000);
            return;
        }
        
        displayRecommendations(data.recommendations);
        goToStep(3);
    })
    .catch(error => {
        hideLoader('step1Loader');
        showError('step1Error', 'Error getting recommendations: ' + error.message);
        // Fall back to preferences-based approach
        setTimeout(() => {
            goToStep(2);
        }, 2000);
    });
}

function displayRecommendations(recommendations) {
    recommendationsContainer.innerHTML = '';
    
    if (!recommendations || recommendations.length === 0) {
        recommendationsContainer.innerHTML = '<p>No recommendations available.</p>';
        return;
    }
    
    recommendations.forEach(car => {
        const carCard = document.createElement('div');
        carCard.className = 'car-card';
        
        // Create star rating
        const starRating = document.createElement('div');
        starRating.className = 'star-rating';
        const fullStars = Math.floor(car.rating);
        const halfStar = car.rating % 1 >= 0.5;
        
        for (let i = 0; i < 5; i++) {
            let starIcon;
            if (i < fullStars) {
                starIcon = '<i class="fas fa-star"></i>';
            } else if (i === fullStars && halfStar) {
                starIcon = '<i class="fas fa-star-half-alt"></i>';
            } else {
                starIcon = '<i class="far fa-star"></i>';
            }
            starRating.innerHTML += starIcon;
        }
        
        // Check if car has an image URL
        const carImageHTML = car.image_url 
            ? `<div class="car-image-container"><img src="${car.image_url}" alt="${car.name}" class="car-image"></div>`
            : '<div class="car-image-container"><div class="no-image">No Image</div></div>'; // Placeholder if no image
        
        carCard.innerHTML = `
            <div class="car-card-content">
                <div class="car-image-section">
                    ${carImageHTML}
                </div>
                <div class="car-info-section">
                    <h3>${car.name}</h3>
                    ${starRating.outerHTML}
                    <div class="car-details">
                        <div class="car-detail"><img src="https://img.icons8.com/?size=100&id=B1m01Ohu23Hh&format=png&color=228BE6" alt="car_icon" width="40" height="40" ><span>Type:</span> ${car.car_type}</div>
                        <div class="car-detail"><img src="https://img.icons8.com/?size=100&id=112254&format=png&color=000000" alt="transmission_icon" width="40" height="40"><span>Transmission:</span> ${car.transmission}</div>
                        <div class="car-detail"><img src="https://img.icons8.com/?size=100&id=9JHIJk60xdLp&format=png&color=000000" alt="Fuel_icon" width="40" height="40"><span>Fuel Policy:</span> ${car.fuel_policy}</div>
                        <div class="car-detail"><img src="https://img.icons8.com/?size=100&id=41152&format=png&color=000000" alt="Mileage_icon" width="40" height="40"><span>Mileage:</span> ${car.mileage_kmpl} kmpl</div>
                        <div class="car-detail"><span class="material-icons">person</span><span>Seats:</span> ${car.occupancy}</div>
                        <div class="car-detail"><img src="https://img.icons8.com/?size=100&id=wgC4n5niQXU_&format=png&color=000000" alt="AC_icon" width="40" height="40"><span>AC:</span> ${car.ac}</div>
                        <div class="car-detail"><img src="https://cdn-icons-png.flaticon.com/128/2028/2028454.png" alt="lugguage_icon" width="40" height="40"><span>Luggage:</span> ${car.luggage_capacity}</div>
                        <div class="car-detail"><img src="https://cdn.iconscout.com/icon/premium/png-512-thumb/car-rental-11566737-9463248.png" alt="agency_icon" width="45" height="45"><span>Agency:</span> ${car.agency_name}</div>
                    </div>
                </div>
            </div>
            <div class="price-booking">
                <div class="price-tag">
                  ₹${car.price_per_day || car.price_per_hour}/${car.price_per_day ? "day" : "hour"}
                </div>
                <div class="booking-options">
                    <select class="rental-days" id="days-${car.id}">
                        ${[1, 2, 3, 5, 7, 14, 30].map(d => `<option value="${d}">${d} day${d > 1 ? 's' : ''}</option>`).join('')}
                    </select>
                     <button class="book-now-btn" data-car-id="${car.id}">Book Now</button>
                </div>
            </div>
        `;
        
        recommendationsContainer.appendChild(carCard);
    });
    document.querySelectorAll('.book-now-btn').forEach(button => {
        button.addEventListener('click', function() {
            const carId = this.getAttribute('data-car-id');
            const daysSelect = document.getElementById(`days-${carId}`);
            const days = daysSelect.value;
            
            // Redirect to confirmation page
            window.location.href = `/confirm_booking/${carId}?days=${days}`;
            
        });
    });
}

function goToStep(step) {
    // Hide all steps
    document.querySelectorAll('.step').forEach(el => {
        el.classList.remove('active');
    });
    
    // Show current step
    document.getElementById(`step${step}`).classList.add('active');
    currentStep = step;
    
    // Clear error messages
    document.querySelectorAll('.error-message').forEach(el => {
        el.style.display = 'none';
    });
}

function showError(elementId, message) {
    const errorElement = document.getElementById(elementId);
    errorElement.textContent = message;
    errorElement.style.display = 'block';
}

function showLoader(elementId) {
    const loaderElement = document.getElementById(elementId);
    loaderElement.style.display = 'block';
}

function hideLoader(elementId) {
    const loaderElement = document.getElementById(elementId);
    loaderElement.style.display = 'none';
}