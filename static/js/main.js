// Global variables
let currentStep = 1;
let currentUserId = null;
let currentLocation = null;
let isExistingUser = false;

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
    const userId = document.getElementById('userId').value.trim();
    const location = locationSelect.value;

    if (!location) {
        showError('step1Error', 'Please select a pickup location');
        return;
    }

    if (userId) {
        // User provided ID, check if they exist
        checkUser(userId, location);
    } else {
        // New user, ask for preferences
        currentUserId = null;
        currentLocation = location;
        isExistingUser = false;
        goToStep(2);
    }
});

preferencesForm.addEventListener('submit', function(e) {
    e.preventDefault();
    const carType = carTypeSelect.value;
    const maxPrice = document.getElementById('maxPrice').value;
    const acRequired = document.getElementById('acRequired').value;
    const unlimitedMileage = document.getElementById('unlimitedMileage').value;

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

function checkUser(userId, location) {
    showLoader('step1Loader');
    fetch('/api/check_user', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: userId, location: location }),
    })
    .then(response => response.json())
    .then(data => {
        hideLoader('step1Loader');
        if (data.error) {
            showError('step1Error', data.error);
            return;
        }
        
        currentUserId = userId;
        currentLocation = location;
        isExistingUser = data.user_exists;
        
        if (isExistingUser) {
            // Existing user - get collaborative recommendations
            getCollaborativeRecommendations(userId, location);
        } else {
            // User ID exists but not at this location, ask for preferences
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
            unlimited_mileage: unlimitedMileage
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
            showError('step1Error', data.error);
            return;
        }
        
        displayRecommendations(data.recommendations);
        goToStep(3);
    })
    .catch(error => {
        hideLoader('step1Loader');
        showError('step1Error', 'Error getting recommendations: ' + error.message);
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
        
        carCard.innerHTML = `
            <h3>${car.model}</h3>
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
            <div class="price-tag">₹${car.price_per_hour}/hour</div>
        `;
        
        recommendationsContainer.appendChild(carCard);
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