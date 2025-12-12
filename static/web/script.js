let loadingTimeoutId; // Stores the timeout ID for the loading indicator

// Shows a delayed loading indicator to prevent flicker on fast loads
function showLoading() {
  clearTimeout(loadingTimeoutId); // Clear any previous loading timeouts

  // Set a timeout to display the loading view after 200ms
  loadingTimeoutId = setTimeout(() => {
    document.getElementById('loading_view').style.display = 'block';
    document.getElementById('requests_view').style.display = 'none';
    document.getElementById('logs_view').style.display = 'none';
  }, 200);
}

// Activates the specified view (requests or raw) and hides others
function show_view(view_name) {
  clearTimeout(loadingTimeoutId); // Clear any pending loading timeouts
  document.getElementById('loading_view').style.display = 'none'; // Hide loading indicator
  document.getElementById('requests_view').style.display = 'none'; // Hide requests view
  document.getElementById('logs_view').style.display = 'none'; // Hide raw view
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
    const logsFormInput = document.getElementById('view_mode_logs_form');
    if (logsFormInput) logsFormInput.value = mode;
    
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
    let today = new Date();
    let startDate, endDate;

    // Helper to parse YYYY-MM-DD in a timezone-safe way
    const parseDate = (dateString) => {
        const parts = dateString.split('-');
        return new Date(parts[0], parts[1] - 1, parts[2]);
    };

    // Use current start_date from the form to calculate next/prev day/week/month
    let current_start_date = parseDate(document.getElementById('start_date').value);
    let current_end_date = parseDate(document.getElementById('end_date').value);

    switch (option) {
        case 'today':
            startDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            endDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            break;
        case 'previous_day':
            current_start_date.setDate(current_start_date.getDate() - 1);
            current_end_date.setDate(current_end_date.getDate() - 1);
            startDate = current_start_date;
            endDate = current_end_date;
            break;
        case 'next_day':
            current_start_date.setDate(current_start_date.getDate() + 1);
            current_end_date.setDate(current_end_date.getDate() + 1);
            startDate = current_start_date;
            endDate = current_end_date;
            break;
        case 'this_week':
            startDate = new Date(today.getFullYear(), today.getMonth(), today.getDate() - today.getDay());
            endDate = new Date(startDate);
            endDate.setDate(startDate.getDate() + 6);
            break;
        case 'previous_week':
            current_start_date.setDate(current_start_date.getDate() - 7);
            current_end_date.setDate(current_end_date.getDate() - 7);
            startDate = current_start_date;
            endDate = current_end_date;
            break;
        case 'next_week':
            current_start_date.setDate(current_start_date.getDate() + 7);
            current_end_date.setDate(current_end_date.getDate() + 7);
            startDate = current_start_date;
            endDate = current_end_date;
            break;
        case 'this_month':
            startDate = new Date(today.getFullYear(), today.getMonth(), 1);
            endDate = new Date(today.getFullYear(), today.getMonth() + 1, 0);
            break;
        case 'previous_month':
            startDate = new Date(current_start_date.getFullYear(), current_start_date.getMonth() - 1, 1);
            endDate = new Date(current_start_date.getFullYear(), current_start_date.getMonth(), 0);
            break;
        case 'next_month':
            startDate = new Date(current_start_date.getFullYear(), current_start_date.getMonth() + 1, 1);
            endDate = new Date(current_start_date.getFullYear(), current_start_date.getMonth() + 2, 0);
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

// --- New Charting Logic for Per App Per Day ---
document.addEventListener('DOMContentLoaded', function() {
    let chartCounter = 0;
    const charts = {}; // To hold chart instances

    const requests_by_day_labels = JSON.parse(document.getElementById('requests_by_day_labels').textContent);
    const requests_by_day_data = JSON.parse(document.getElementById('requests_by_day_data').textContent);
    const junk_requests_by_day_data = JSON.parse(document.getElementById('junk_requests_by_day_data').textContent);

    function updateChartControls() {
        const chartContainers = document.querySelectorAll('#comparison-charts-container .chart-container');
        const showControls = chartContainers.length > 1;
        chartContainers.forEach(container => {
            const moveUpBtn = container.querySelector('.move-up-btn');
            const moveDownBtn = container.querySelector('.move-down-btn');
            const removeBtn = container.querySelector('.remove-chart-btn');
            
            if (moveUpBtn) moveUpBtn.style.display = showControls ? 'inline-block' : 'none';
            if (moveDownBtn) moveDownBtn.style.display = showControls ? 'inline-block' : 'none';
            if (removeBtn) removeBtn.style.display = showControls ? 'inline-block' : 'none';
        });
    }

    // Function to render the chart
    function renderChart(canvasId, selectedApp, isJunk = false) {
        const ctx = document.getElementById(canvasId).getContext('2d');
        
        if (charts[canvasId]) {
            charts[canvasId].destroy(); // Destroy previous chart instance
        }

        const datasetLabel = isJunk ? `Total Junk Requests for ${selectedApp}` : `Total Requests for ${selectedApp}`;
        const datasetData = isJunk ? junk_requests_by_day_data[selectedApp] : requests_by_day_data[selectedApp];
        const bgColor = isJunk ? 'rgba(255, 99, 132, 0.2)' : 'rgba(54, 162, 235, 0.2)';
        const borderColor = isJunk ? 'rgba(255, 99, 132, 1)' : 'rgba(54, 162, 235, 1)';

        charts[canvasId] = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: requests_by_day_labels,
                datasets: [{
                    label: datasetLabel,
                    data: datasetData,
                    backgroundColor: bgColor,
                    borderColor: borderColor,
                    borderWidth: 1
                }]
            },
            options: {
                scales: {
                    y: {
                        beginAtZero: true
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                },
                animation: {
                    duration: 0
                }
            }
        });
    }

    function addChartEventListeners(chartContainer, chartId, junkChartId) {
        const moveUpButton = chartContainer.querySelector('.move-up-btn');
        const moveDownButton = chartContainer.querySelector('.move-down-btn');
        const removeButton = chartContainer.querySelector('.remove-chart-btn');
        const toggleJunkButton = chartContainer.querySelector('.toggle-junk-btn');

        if (moveUpButton) {
            moveUpButton.addEventListener('click', () => {
                const parent = chartContainer.parentNode;
                if (chartContainer.previousElementSibling) {
                    parent.insertBefore(chartContainer, chartContainer.previousElementSibling);
                }
            });
        }

        if (moveDownButton) {
            moveDownButton.addEventListener('click', () => {
                const parent = chartContainer.parentNode;
                if (chartContainer.nextElementSibling) {
                    parent.insertBefore(chartContainer.nextElementSibling, chartContainer);
                }
            });
        }
        
        if (removeButton) {
            removeButton.addEventListener('click', () => {
                if (charts[chartId]) {
                    charts[chartId].destroy();
                    delete charts[chartId];
                }
                if (charts[junkChartId]) {
                    charts[junkChartId].destroy();
                    delete charts[junkChartId];
                }
                chartContainer.remove();
                updateChartControls();
            });
        }

        if (toggleJunkButton) {
            toggleJunkButton.addEventListener('click', () => {
                const junkWrapper = chartContainer.querySelector('.junk-chart-wrapper');
                if (junkWrapper.style.display === 'none') {
                    junkWrapper.style.display = 'block';
                    toggleJunkButton.textContent = 'Hide Junk';
                } else {
                    junkWrapper.style.display = 'none';
                    toggleJunkButton.textContent = 'Show Junk';
                }
            });
        }
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
        
        // Render initial charts
        renderChart('requests_by_day_chart', SELECTED_APPS[0], false);
        renderChart('junk_requests_by_day_chart', SELECTED_APPS[0], true);

        initialAppSelector.addEventListener('change', (event) => {
            renderChart('requests_by_day_chart', event.target.value, false);
            renderChart('junk_requests_by_day_chart', event.target.value, true);
        });
        
        addChartEventListeners(initialChartContainer, 'requests_by_day_chart', 'junk_requests_by_day_chart');
    } else {
        initialChartContainer.style.display = 'none';
    }


    // "Compare another app" button
    document.getElementById('add-comparison-chart-btn').addEventListener('click', () => {
        chartCounter++;
        const newChartId = `comparison_chart_${chartCounter}`;
        const newJunkChartId = `junk_comparison_chart_${chartCounter}`;
        const newSelectorId = `comparison_selector_${chartCounter}`;
        
        const newChartContainer = document.createElement('div');
        newChartContainer.id = `chart-container-${chartCounter}`;
        newChartContainer.className = 'chart-container';
        newChartContainer.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <label for="${newSelectorId}">Select App:</label>
                    <select id="${newSelectorId}"></select>
                </div>
                <div class="chart-controls">
                    <button class="toggle-junk-btn">Show Junk</button>
                    <button class="move-up-btn">Move Up</button>
                    <button class="move-down-btn">Move Down</button>
                    <button class="remove-chart-btn" data-chart-id="${newChartId}">Remove</button>
                </div>
            </div>
            <canvas id="${newChartId}" width="400" height="100"></canvas>
            <div class="junk-chart-wrapper" style="display: none; margin-top: 10px; border-top: 1px dashed #ccc; padding-top: 10px;">
                <h5 style="margin-top: 0;">Junk Traffic</h5>
                <canvas id="${newJunkChartId}" width="400" height="100"></canvas>
            </div>
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
            
            renderChart(newChartId, SELECTED_APPS[0], false);
            renderChart(newJunkChartId, SELECTED_APPS[0], true);
            
            newSelector.addEventListener('change', (event) => {
                renderChart(newChartId, event.target.value, false);
                renderChart(newJunkChartId, event.target.value, true);
            });
            
            addChartEventListeners(newChartContainer, newChartId, newJunkChartId);
        }
        updateChartControls();
    });

    updateChartControls();
});

// Dark mode toggle
function toggle_dark_mode() {
    const body = document.body;
    body.classList.toggle('dark-mode');
    const isDarkMode = body.classList.contains('dark-mode');
    localStorage.setItem('dark-mode', isDarkMode);
    document.getElementById('checkbox').checked = isDarkMode;
}

document.addEventListener('DOMContentLoaded', function() {
    const isDarkMode = localStorage.getItem('dark-mode') === 'true';
    if (isDarkMode) {
        document.body.classList.add('dark-mode');
        document.getElementById('checkbox').checked = true;
    }
});
