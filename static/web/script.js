let loadingTimeoutId; // Stores the timeout ID for the loading indicator

// Shows a delayed loading indicator to prevent flicker on fast loads
function showLoading() {
  clearTimeout(loadingTimeoutId); // Clear any previous loading timeouts

  // Set a timeout to display the loading view after 200ms
  loadingTimeoutId = setTimeout(() => {
    document.getElementById('loading_view').style.display = 'block';
    document.getElementById('summary_view').style.display = 'none';
    document.getElementById('tail_view').style.display = 'none';
  }, 200);
}

// Activates the specified view (summary or tail) and hides others
function show_view(view_name) {
  clearTimeout(loadingTimeoutId); // Clear any pending loading timeouts
  document.getElementById('loading_view').style.display = 'none'; // Hide loading indicator
  document.getElementById('summary_view').style.display = 'none'; // Hide summary view
  document.getElementById('tail_view').style.display = 'none'; // Hide tail view
  document.getElementById('uptime_view').style.display = 'none'; // Hide uptime view
  document.getElementById(view_name + '_view').style.display = 'block'; // Display the selected view
}

// Function to set the view mode in hidden input fields and activate the corresponding view
function set_view_mode_and_show(mode) {
    // Update the hidden view_mode input in the app selection form
    const appsFormInput = document.getElementById('view_mode_apps_form');
    if (appsFormInput) appsFormInput.value = mode;

    // Update the hidden view_mode input in the date/top N selection form
    const dateFormInput = document.getElementById('view_mode_date_form');
    if (dateFormInput) dateFormInput.value = mode;

    // Update the hidden view_mode input in the tail log form
    const tailFormInput = document.getElementById('view_mode_tail_form');
    if (tailFormInput) tailFormInput.value = mode;
    
    // Activate the selected view
    show_view(mode);
}

// The select_app function is no longer used with the new table layout.

// Selects a single application and submits the form
function select_single_app(app_name) {
    // Uncheck all app checkboxes first
    const all_checkboxes = document.querySelectorAll('.app-checkbox');
    all_checkboxes.forEach(checkbox => {
        checkbox.checked = false;
    });

    // Check only the selected one
    const checkbox = document.getElementById(`app_${app_name}`);
    if (checkbox) {
        checkbox.checked = true;
    }

    showLoading(); // Show loading indicator
    document.getElementById('select_apps_form').submit(); // Submit the form
}

// Generic function to set the checked state for a list of apps
function set_apps_checked_state(apps_list, is_checked) {
    apps_list.forEach(appName => {
        const checkbox = document.getElementById(`app_${appName}`);
        if (checkbox) {
            checkbox.checked = is_checked;
        }
    });
}

// Selects or deselects all applications
function select_all_apps(is_checked) {
    set_apps_checked_state(ALL_APPS, is_checked);
}

// Selects or deselects all production applications
function select_all_prd(is_checked) {
    set_apps_checked_state(PRD_APPS, is_checked);
}

// Selects or deselects all staging applications
function select_all_stg(is_checked) {
    set_apps_checked_state(STG_APPS, is_checked);
}
// Event listener for the "Find Locations" button
document.getElementById('find-locations-btn').addEventListener('click', function() {
    this.disabled = true; // Disable button to prevent multiple clicks
    this.textContent = '...'; // Change button text to indicate loading

    // Iterate over each IP row in the table
    document.querySelectorAll('.ip-row').forEach(row => {
        const ip = row.dataset.ip; // Get IP from data attribute
        const locationCell = row.querySelector('.geo-location');
        locationCell.textContent = 'Loading...'; // Show loading text in location cell

        // Fetch geolocation data for the IP
        fetch(`/api/geo/${ip}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    // Display error if API returns one
                    locationCell.innerHTML = `<span class="text-danger" title="${data.error}">Error</span>`;
                } else if (data.status === 'success') {
                    // Display formatted location if successful
                    const locationParts = [data.city, data.regionName, data.country].filter(Boolean);
                    locationCell.textContent = locationParts.join(', ') || '?';
                } else {
                    // Indicate unknown status
                    locationCell.textContent = 'Unknown';
                }
            })
            .catch(error => {
                // Log and display fetch errors
                console.error('Error fetching geo location:', error);
                locationCell.innerHTML = `<span class="text-danger" title="${error}">Error</span>`;
            });
    });
});

function toggle_ua_counts() {
    var wrapper = document.getElementById("ua_counts_wrapper");
    if (wrapper.style.display === "none") {
        wrapper.style.display = "block";
    } else {
        wrapper.style.display = "none";
    }
}
