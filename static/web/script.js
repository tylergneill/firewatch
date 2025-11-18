let loadingTimeoutId; // Declare a variable to hold the timeout ID

function showLoading() {
  // Clear any previous timeout if an action is initiated again quickly
  clearTimeout(loadingTimeoutId);

  // Set a timeout to show the loading view after 200ms
  loadingTimeoutId = setTimeout(() => {
    document.getElementById('loading_view').style.display = 'block';
    document.getElementById('summary_view').style.display = 'none';
    document.getElementById('tail_view').style.display = 'none';
  }, 200);
}

function show_view(view_name) {
  // When a view is shown, ensure the loading view is hidden and clear any pending timeout
  clearTimeout(loadingTimeoutId);
  document.getElementById('loading_view').style.display = 'none';
  document.getElementById('summary_view').style.display = 'none';
  document.getElementById('tail_view').style.display = 'none';
  document.getElementById(view_name + '_view').style.display = 'block';
}

window.onload = () => {
  // When the page finishes loading, clear any pending loading timeout
  clearTimeout(loadingTimeoutId);
  // And then show the default view (summary)
  show_view('summary');
};

function select_app(app_name) {
  var checkboxes = document.getElementsByName('apps');
  for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].checked = checkboxes[i].value === app_name;
  }
  showLoading(); // Initiate delayed loading indicator
  document.getElementById('select_apps_form').submit();
}

function select_all_apps() {
  var checkboxes = document.getElementsByName('apps');
  for (var i = 0; i < checkboxes.length; i++) {
      checkboxes[i].checked = true;
  }
}
document.getElementById('find-locations-btn').addEventListener('click', function() {
    this.disabled = true;
    this.textContent = '...';

    document.querySelectorAll('.ip-row').forEach(row => {
        const ip = row.dataset.ip;
        const locationCell = row.querySelector('.geo-location');
        locationCell.textContent = 'Loading...';

        fetch(`/api/geo/${ip}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    locationCell.innerHTML = `<span class="text-danger" title="${data.error}">Error</span>`;
                } else if (data.status === 'success') {
                    const locationParts = [data.city, data.regionName, data.country].filter(Boolean);
                    locationCell.textContent = locationParts.join(', ') || '?';
                } else {
                    locationCell.textContent = 'Unknown';
                }
            })
            .catch(error => {
                console.error('Error fetching geo location:', error);
                locationCell.innerHTML = `<span class="text-danger" title="${error}">Error</span>`;
            });
    });
});