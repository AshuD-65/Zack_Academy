// Course Material Admin - Dynamic Field Display
// This script shows/hides content fields based on material type selection

function toggleContentFields(materialType) {
    const fileField = document.querySelector('input[name="file"]').closest('.form-row');
    const externalUrlField = document.querySelector('input[name="external_url"]').closest('.form-row');
    const contentDescription = document.querySelector('.form-row .help');
    
    if (materialType === 'VIDEO') {
        // For Video File - show both file upload and external URL
        if (fileField) {
            fileField.style.display = 'block';
            const fileLabel = fileField.querySelector('label');
            if (fileLabel) fileLabel.textContent = 'Video File:';
        }
        
        if (externalUrlField) {
            externalUrlField.style.display = 'block';
            const urlLabel = externalUrlField.querySelector('label');
            if (urlLabel) urlLabel.textContent = 'External Video URL:';
        }
        
        if (contentDescription) {
            contentDescription.textContent = 'Upload a video file OR provide an external URL (YouTube, Vimeo, etc.)';
        }
    } else if (materialType === 'PDF') {
        // For File - show both file upload and external URL
        if (fileField) {
            fileField.style.display = 'block';
            const fileLabel = fileField.querySelector('label');
            if (fileLabel) fileLabel.textContent = 'Document File:';
        }
        
        if (externalUrlField) {
            externalUrlField.style.display = 'block';
            const urlLabel = externalUrlField.querySelector('label');
            if (urlLabel) urlLabel.textContent = 'External Document URL:';
        }
        
        if (contentDescription) {
            contentDescription.textContent = 'Upload a document file OR provide an external URL (PDF, DOC, etc.)';
        }
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    const materialTypeSelect = document.querySelector('select[name="material_type"]');
    if (materialTypeSelect) {
        // Set initial state
        toggleContentFields(materialTypeSelect.value);
        
        // Add change event listener
        materialTypeSelect.addEventListener('change', function() {
            toggleContentFields(this.value);
        });
    }
});

