document.addEventListener('DOMContentLoaded', () => {
    // ---ELEMENT SELECTORS---
    const loginPage = document.getElementById('login-page');
    const mainApp = document.getElementById('main-app');
    const dashboardView = document.getElementById('dashboard-view');
    const profileView = document.getElementById('profile-view');
    const dashboardBtn = document.getElementById('dashboard-btn');
    const profileBtn = document.getElementById('profile-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const loginForm = document.getElementById('login-form');
    const delayForm = document.getElementById('delay-form');
    const optimizeForm = document.getElementById('optimize-form');
    const transportForm = document.getElementById('transport-form');
    const resultsSection = document.getElementById('results-section');
    const resultsContent = document.getElementById('results-content');
    const resultsTitle = document.getElementById('results-title');
    const editProfileBtn = document.getElementById('edit-profile-btn');
    const editProfileModal = document.getElementById('edit-profile-modal');
    const cancelEditBtn = document.getElementById('cancel-edit-btn');
    const editProfileForm = document.getElementById('edit-profile-form');
    const editVehicleModal = document.getElementById('edit-vehicle-modal');
    const editVehicleTitle = document.getElementById('edit-vehicle-title');
    const cancelEditVehicleBtn = document.getElementById('cancel-edit-vehicle-btn');
    const editVehicleForm = document.getElementById('edit-vehicle-form');
    const editVehicleBtns = document.querySelectorAll('.edit-vehicle-btn');

    // --- MAP INITIALIZATION ---
    // Centered on India, zoom level 5
    const map = L.map('map').setView([22.5937, 78.9629], 5);
    
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 19
    }).addTo(map);

    // The line for the default Agra marker has been removed.
    
    let routeLayerGroup = L.layerGroup().addTo(map);

    // --- DATA & STATE MANAGEMENT ---
    const profileElements = { name: document.getElementById('profile-name'), email: document.getElementById('profile-email'), age: document.getElementById('profile-age'), gender: document.getElementById('profile-gender'), nationality: document.getElementById('profile-nationality'), license: document.getElementById('profile-license'), address: document.getElementById('profile-address'), };
    const modalInputs = { name: document.getElementById('modal-name'), email: document.getElementById('modal-email'), age: document.getElementById('modal-age'), gender: document.getElementById('modal-gender'), nationality: document.getElementById('modal-nationality'), license: document.getElementById('modal-license'), address: document.getElementById('modal-address'), };
    const vehicleElements = { car: { plate: document.getElementById('car-plate'), model: document.getElementById('car-model'), color: document.getElementById('car-color'), }, bike: { plate: document.getElementById('bike-plate'), model: document.getElementById('bike-model'), color: document.getElementById('bike-color'), } };
    const vehicleModalInputs = { type: document.getElementById('modal-vehicle-type'), plate: document.getElementById('modal-vehicle-plate'), model: document.getElementById('modal-vehicle-model'), color: document.getElementById('modal-vehicle-color'), };

    // --- UI FUNCTIONS ---
    function showView(view) {
        dashboardView.classList.add('hidden');
        profileView.classList.add('hidden');
        view.classList.remove('hidden');
        [dashboardBtn, profileBtn].forEach(b => { b.classList.remove('text-white', 'border-purple-400', 'pb-1'); b.classList.add('text-gray-400'); });
        const btn = view === dashboardView ? dashboardBtn : profileBtn;
        btn.classList.add('text-white', 'border-purple-400', 'pb-1');
        btn.classList.remove('text-gray-400');
        if (view === dashboardView) { setTimeout(() => map.invalidateSize(), 1); }
    }

    function showResults(title, content, isLoading = false) {
        resultsSection.classList.remove('hidden');
        resultsTitle.textContent = title;
        resultsContent.innerHTML = isLoading ? `<div class="flex items-center justify-center space-x-3"><i class="fas fa-spinner fa-spin text-2xl text-purple-400"></i><span class="text-lg">Analyzing...</span></div>` : content;
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function drawRouteOnMap(stops, routePath) {
        routeLayerGroup.clearLayers();
        if (!stops || stops.length === 0) return;
        if (routePath && routePath.length > 0) {
            const polyline = L.polyline(routePath, { color: '#805ad5', weight: 4, className: 'animated-route' }).addTo(routeLayerGroup);
            map.fitBounds(polyline.getBounds().pad(0.1));
        }
        stops.forEach((stop, index) => { L.marker([stop.lat, stop.lon]).addTo(routeLayerGroup).bindPopup(`<b>${index + 1}. ${stop.name}</b>`).openPopup(); });
    }
    
    // --- EVENT LISTENERS ---
    dashboardBtn.addEventListener('click', () => showView(dashboardView));
    profileBtn.addEventListener('click', () => showView(profileView));
    loginForm.addEventListener('submit', (e) => { e.preventDefault(); loginPage.classList.add('hidden'); mainApp.classList.remove('hidden'); showView(dashboardView); });
    logoutBtn.addEventListener('click', () => { mainApp.classList.add('hidden'); loginPage.classList.remove('hidden'); });
    
    // --- API INTEGRATION ---
    delayForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        showResults('Delay Prediction Result', '', true);
        const origin = document.getElementById('origin-input').value;
        const destination = document.getElementById('destination-input').value;
        const departureTime = document.getElementById('departure-time-input').value;
        const formattedTimestamp = departureTime.replace('T', ' ');
        try {
            const response = await fetch('/predict-delay', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ origin, destination, timestamp: formattedTimestamp }) });
            if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.detail || 'Backend error'); }
            const data = await response.json();
            
            const resultHTML = `<div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center"><div><p class="text-sm text-gray-400">Base Travel Time</p><p class="text-2xl font-bold text-white">${Math.round(data.base_travel_minutes)} min</p></div><div><p class="text-sm text-gray-400">Predicted Delay</p><p class="text-2xl font-bold text-purple-300">+${data.predicted_delay_minutes.toFixed(1)} min</p></div><div><p class="text-sm text-gray-400">Weather</p><p class="text-2xl font-bold text-white capitalize">${data.weather}</p></div><div><p class="text-sm text-gray-400">Total Estimated Time</p><p class="text-2xl font-bold text-green-400">${Math.round(data.total_estimated_time)} min</p></div></div>`;
            showResults('Delay Prediction Result', resultHTML);

            drawRouteOnMap(data.stops, data.route_path);

        } catch (error) { showResults('Error', `<p class="text-red-400">Could not fetch prediction: ${error.message}</p>`); }
    });
    
    optimizeForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        showResults('Optimized Route', '', true);
        const destinations = document.getElementById('destinations-textarea').value.trim().split('\n').filter(d => d).map(address => ({ address }));
        if (destinations.length < 2) { showResults('Error', `<p class="text-red-400">Please enter at least 2 destinations.</p>`); return; }
        try {
            const response = await fetch('/optimize-route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ stops: destinations }) });
            if (!response.ok) { const errorData = await response.json(); throw new Error(errorData.detail || 'Backend error'); }
            const data = await response.json();
            const resultHTML = `<ol class="list-decimal list-inside space-y-2">${data.optimized_stops.map(d => `<li class="text-lg p-2 bg-gray-800/40 rounded-md">${d.name}</li>`).join('')}</ol>`;
            showResults('Optimized Route', resultHTML);
            drawRouteOnMap(data.optimized_stops, data.route_path);
        } catch (error) { showResults('Error', `<p class="text-red-400">Could not optimize route: ${error.message}</p>`); }
    });

    // --- TRANSPORT FINDER ---
    transportForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const origin = document.getElementById('transport-origin-input').value;
        const dest = document.getElementById('transport-destination-input').value;
        showResults(`Transport Options: ${origin} to ${dest}`, '', true);
        try {
            const response = await fetch('/find-transport', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ origin, destination: dest }) });
            if (!response.ok) throw new Error('Could not fetch transport options from the server.');
            const transports = await response.json();
            if (transports.length === 0) { showResults(`Transport Options: ${origin} to ${dest}`, '<p class="text-center text-gray-400">No direct transport options found for this route.</p>'); return; }
            const groupedByType = transports.reduce((acc, t) => { const type = t.transport_type; if (!acc[type]) acc[type] = []; acc[type].push(t); return acc; }, {});
            let resultHTML = '<div class="space-y-4">';
            const iconMap = { flight: 'fa-plane-departure', train: 'fa-train', bus: 'fa-bus-simple' };
            const titleMap = { flight: 'Flights', train: 'Trains', bus: 'Buses' };
            for (const type in groupedByType) {
                const options = groupedByType[type];
                const iconClass = iconMap[type] || 'fa-ticket-alt';
                resultHTML += `<div class="glassmorphism-card rounded-lg overflow-hidden border-l-4 border-purple-500"><button class="accordion-header w-full flex justify-between items-center p-4 text-left"><div class="flex items-center gap-4"><i class="fas ${iconClass} text-2xl text-purple-400 w-8 text-center"></i><div><p class="font-bold text-lg text-white">${titleMap[type]}</p><p class="text-sm text-gray-400">${options.length} options found</p></div></div><i class="fas fa-chevron-down transition-transform duration-300"></i></button><div class="accordion-content"><div class="p-4 space-y-3 border-t border-gray-700/50">`;
                options.forEach((t) => { resultHTML += `<div class="bg-gray-800/50 p-3 rounded-lg"><div class="flex flex-col sm:flex-row items-center justify-between gap-2"><div><p class="font-semibold text-white">${t.operator_name}</p><p class="text-xs text-gray-400">${t.departure_time} → ${t.arrival_time} (${t.duration})</p></div><p class="font-bold text-lg text-green-400 whitespace-nowrap">₹${t.fare.toLocaleString()}</p></div></div>`; });
                resultHTML += `</div></div></div>`;
            }
            resultHTML += '</div>';
            showResults(`Transport Options: ${origin} to ${dest}`, resultHTML);
        } catch (error) { showResults('Error', `<p class="text-red-400">${error.message}</p>`); }
    });

    // --- ACCORDION CLICK HANDLER ---
    resultsContent.addEventListener('click', (e) => {
        const header = e.target.closest('.accordion-header');
        if (header) {
            const content = header.nextElementSibling;
            const icon = header.querySelector('.fa-chevron-down');
            icon.classList.toggle('rotate-180');
            if (content.style.maxHeight) { content.style.maxHeight = null; } else { content.style.maxHeight = content.scrollHeight + "px"; }
        }
    });

    // --- MODAL AND TAB LOGIC ---
    function openEditModal() { Object.keys(modalInputs).forEach(key => modalInputs[key].value = profileElements[key].textContent); editProfileModal.classList.remove('hidden'); }
    function closeEditModal() { editProfileModal.classList.add('hidden'); }
    editProfileBtn.addEventListener('click', openEditModal);
    cancelEditBtn.addEventListener('click', closeEditModal);
    editProfileForm.addEventListener('submit', (e) => { e.preventDefault(); Object.keys(profileElements).forEach(key => profileElements[key].textContent = modalInputs[key].value); closeEditModal(); });
    function openEditVehicleModal(type) { const data = vehicleElements[type], capType = type.charAt(0).toUpperCase() + type.slice(1); editVehicleTitle.textContent = `Edit ${capType} Details`; vehicleModalInputs.type.value = type; Object.keys(data).forEach(key => vehicleModalInputs[key].value = data[key].textContent); editVehicleModal.classList.remove('hidden'); }
    function closeEditVehicleModal() { editVehicleModal.classList.add('hidden'); }
    editVehicleBtns.forEach(btn => btn.addEventListener('click', () => openEditVehicleModal(btn.dataset.vehicle)));
    cancelEditVehicleBtn.addEventListener('click', closeEditVehicleModal);
    editVehicleForm.addEventListener('submit', (e) => { e.preventDefault(); const type = vehicleModalInputs.type.value; if (type) Object.keys(vehicleElements[type]).forEach(key => vehicleElements[type][key].textContent = vehicleModalInputs[key].value); closeEditVehicleModal(); });
    [editProfileModal, editVehicleModal].forEach(modal => modal.addEventListener('click', e => { if (e.target === modal) modal.classList.add('hidden'); }));
    const vehicleTabBtns = document.querySelectorAll('.vehicle-tab-btn');
    const vehicleContents = document.querySelectorAll('.vehicle-content');
    vehicleTabBtns.forEach(btn => btn.addEventListener('click', () => { vehicleTabBtns.forEach(b => b.classList.remove('active')); btn.classList.add('active'); vehicleContents.forEach(c => c.classList.toggle('hidden', c.id !== `${btn.id.split('-')[0]}-content`)); }));
    document.querySelectorAll('.challan-tab-btn').forEach(btn => btn.addEventListener('click', () => { const parent = btn.closest('.vehicle-content'); parent.querySelectorAll('.challan-tab-btn').forEach(b => b.classList.remove('active')); btn.classList.add('active'); parent.querySelectorAll('.challan-content').forEach(c => c.classList.toggle('hidden', c.id !== btn.dataset.target)); }));
});

