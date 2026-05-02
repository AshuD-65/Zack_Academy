// Course Material Admin - Dynamic Field Display
// This script shows/hides content fields based on material type selection

function toggleContentFields(materialTypeSelect) {
    const container = materialTypeSelect.closest('.inline-related') || materialTypeSelect.closest('.form-row') || document;
    const fileField = container.querySelector('input[name$="file"]');
    const externalUrlField = container.querySelector('input[name$="external_url"]');
    const fileRow = fileField ? fileField.closest('.form-row') : null;
    const externalUrlRow = externalUrlField ? externalUrlField.closest('.form-row') : null;
    const contentDescription = container.querySelector('.help');
    const materialType = materialTypeSelect.value;

    if (materialType === 'VIDEO') {
        if (fileRow) {
            fileRow.style.display = 'block';
            const fileLabel = fileRow.querySelector('label');
            if (fileLabel) fileLabel.textContent = 'Video File:';
        }

        if (externalUrlRow) {
            externalUrlRow.style.display = 'block';
            const urlLabel = externalUrlRow.querySelector('label');
            if (urlLabel) urlLabel.textContent = 'External Video URL:';
        }

        if (contentDescription) {
            contentDescription.textContent = 'Upload a video file OR provide an external URL (YouTube, Vimeo, etc.)';
        }
    } else if (materialType === 'PDF') {
        if (fileRow) {
            fileRow.style.display = 'block';
            const fileLabel = fileRow.querySelector('label');
            if (fileLabel) fileLabel.textContent = 'Document File:';
        }

        if (externalUrlRow) {
            externalUrlRow.style.display = 'block';
            const urlLabel = externalUrlRow.querySelector('label');
            if (urlLabel) urlLabel.textContent = 'External Document URL:';
        }

        if (contentDescription) {
            contentDescription.textContent = 'Upload a document file OR provide an external URL (PDF, DOC, etc.)';
        }
    } else {
        if (fileRow) fileRow.style.display = 'none';
        if (externalUrlRow) externalUrlRow.style.display = 'none';
        if (contentDescription) contentDescription.textContent = '';
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    const materialTypeSelects = document.querySelectorAll('select[name$="material_type"]');
    materialTypeSelects.forEach(function(materialTypeSelect) {
        toggleContentFields(materialTypeSelect);
        materialTypeSelect.addEventListener('change', function() {
            toggleContentFields(this);
        });
    });
});

