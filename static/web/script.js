let loadingTimeoutId; // Stores the timeout ID for the loading indicator

// Shows a delayed loading indicator to prevent flicker on fast loads
function showLoading() {
  clearTimeout(loadingTimeoutId); // Clear any previous loading timeouts

  // Set a timeout to display the loading view after 200ms
  loadingTimeoutId = setTimeout(() => {
    document.getElementById('loading_view').style.display = 'block';
    document.getElementById('requests_view').style.display = 'none';
    document.getElementById('raw_view').style.display = 'none';
  }, 200);
}

// Activates the specified view (requests or raw) and hides others
function show_view(view_name) {
  clearTimeout(loadingTimeoutId); // Clear any pending loading timeouts
  document.getElementById('loading_view').style.display = 'none'; // Hide loading indicator
  document.getElementById('requests_view').style.display = 'none'; // Hide requests view
  document.getElementById('raw_view').style.display = 'none'; // Hide raw view
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

    // Update the hidden view_mode input in the raw log form
    const rawFormInput = document.getElementById('view_mode_raw_form');
    if (rawFormInput) rawFormInput.value = mode;
    
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

function toggle_collapsible(elementId) {
    var wrapper = document.getElementById(elementId);
    if (wrapper.style.display === "none") {
        wrapper.style.display = "block";
    } else {
        wrapper.style.display = "none";
    }
}

// New function to set quick date ranges
function setQuickDate(option) {
    const today = new Date();
    let startDate = new Date(today);
    let endDate = new Date(today);

    switch (option) {
        case 'today':
            // start and end date are already today
            break;
        case 'yesterday':
            startDate.setDate(today.getDate() - 1);
            endDate.setDate(today.getDate() - 1);
            break;
        case 'last_week':
            startDate.setDate(today.getDate() - 6); // Last 7 days including today
            break;
        case 'last_month':
            startDate.setMonth(today.getMonth() - 1);
            // endDate remains today
            break;
        case 'last_3_months':
            startDate.setMonth(today.getMonth() - 3);
            // endDate remains today
            break;
        default:
            return;
    }

    // Format dates to YYYY-MM-DD for input fields
    const formatDate = (date) => date.toISOString().split('T')[0];

    document.getElementById('start_date').value = formatDate(startDate);
    document.getElementById('end_date').value = formatDate(endDate);

    // Automatically submit the form
    document.getElementById('view_mode_date_form').closest('form').submit();
}

function show_bottom_view(view_name) {
    // Hide all bottom views
    const views = document.querySelectorAll('.bottom_view');
    views.forEach(view => {
        view.style.display = 'none';
    });

    // Show the selected one
    const selected_view = document.getElementById('bottom_view_' + view_name);
    if (selected_view) {
        selected_view.style.display = 'block';
    }
}

// --- New Charting Logic for Total Requests by Day ---
document.addEventListener('DOMContentLoaded', function() {
    let chartCounter = 0;
    const charts = {}; // To hold chart instances

    // Function to fetch data and render the chart
    function renderRequestsByDayChart(canvasId, selectedApp) {
        const startDate = document.getElementById('start_date').value;
        const endDate = document.getElementById('end_date').value;

        fetch(`/api/requests_by_day?app=${selectedApp}&start_date=${startDate}&end_date=${endDate}`)
            .then(response => response.json())
            .then(data => {
                const ctx = document.getElementById(canvasId).getContext('2d');
                
                if (charts[canvasId]) {
                    charts[canvasId].destroy(); // Destroy previous chart instance
                }

                charts[canvasId] = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: `Total Requests for ${selectedApp}`,
                            data: data.values,
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            borderColor: 'rgba(54, 162, 235, 1)',
                            borderWidth: 1
                        }]
                    },
                    options: {
                        scales: {
                            y: {
                                beginAtZero: true
                            }
                        }
                    }
                });
            })
            .catch(error => console.error('Error fetching requests by day data:', error));
    }

    function addChartEventListeners(chartContainer, chartId) {
        const moveUpButton = chartContainer.querySelector('.move-up-btn');
        const moveDownButton = chartContainer.querySelector('.move-down-btn');
        const removeButton = chartContainer.querySelector('.remove-chart-btn');

        moveUpButton.addEventListener('click', () => {
            const parent = chartContainer.parentNode;
            if (chartContainer.previousElementSibling) {
                parent.insertBefore(chartContainer, chartContainer.previousElementSibling);
            }
        });

        moveDownButton.addEventListener('click', () => {
            const parent = chartContainer.parentNode;
            if (chartContainer.nextElementSibling) {
                parent.insertBefore(chartContainer.nextElementSibling, chartContainer);
            }
        });
        
        removeButton.addEventListener('click', () => {
            if (charts[chartId]) {
                charts[chartId].destroy(); // Destroy Chart.js instance
                delete charts[chartId]; // Remove from charts object
            }
            chartContainer.remove(); // Remove the entire container from DOM
        });
    }

    // Initial chart
    const initialChartContainer = document.getElementById('chart-container-0');
    const initialAppSelector = document.getElementById('requests_by_day_app_selector');
    if (SELECTED_APPS.length > 0) {
        SELECTED_APPS.forEach(app => {
            const option = document.createElement('option');
            option.value = app;
            option.textContent = app;
            initialAppSelector.appendChild(option);
        });
        renderRequestsByDayChart('requests_by_day_chart', SELECTED_APPS[0]);
        initialAppSelector.addEventListener('change', (event) => {
            renderRequestsByDayChart('requests_by_day_chart', event.target.value);
        });
        addChartEventListeners(initialChartContainer, 'requests_by_day_chart');
    } else {
        // If there are no selected apps, hide the initial chart container
        initialChartContainer.style.display = 'none';
    }


    // "Compare another app" button
    document.getElementById('add-comparison-chart-btn').addEventListener('click', () => {
        chartCounter++;
        const newChartId = `comparison_chart_${chartCounter}`;
        const newSelectorId = `comparison_selector_${chartCounter}`;
        
        const newChartContainer = document.createElement('div');
        newChartContainer.id = `chart-container-${chartCounter}`; // Add an ID to the container
        newChartContainer.innerHTML = `
            <label for="${newSelectorId}">Select App:</label>
            <select id="${newSelectorId}"></select>
            <div style="float: right;">
                <button class="move-up-btn">Move Up</button>
                <button class="move-down-btn">Move Down</button>
                <button class="remove-chart-btn" data-chart-id="${newChartId}">Remove</button>
            </div>
            <canvas id="${newChartId}" width="400" height="100"></canvas>
            <hr>
        `;
        
        document.getElementById('comparison-charts-container').appendChild(newChartContainer);
        
        const newSelector = document.getElementById(newSelectorId);
        if (SELECTED_APPS.length > 0) {
            SELECTED_APPS.forEach(app => {
                const option = document.createElement('option');
                option.value = app;
                option.textContent = app;
                newSelector.appendChild(option);
            });
            renderRequestsByDayChart(newChartId, SELECTED_APPS[0]);
            newSelector.addEventListener('change', (event) => {
                renderRequestsByDayChart(newChartId, event.target.value);
            });
            addChartEventListeners(newChartContainer, newChartId);
        }
    });
});
