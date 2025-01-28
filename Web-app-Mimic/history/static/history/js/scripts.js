// Retrieve CSRF token from cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.startsWith(name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

const csrfToken = getCookie('csrftoken');

// Handle the history generation
const historyForm = document.getElementById('generate-history-form');
const historyOutput = document.getElementById('history-output');
const hiddenHistory = document.getElementById('hidden-history');

if (historyForm) {
    historyForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const response = await fetch('/generate-history/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
            },
        });
        const data = await response.json();
        if (data.history) {
            historyOutput.textContent = data.history;
            hiddenHistory.value = data.history;
        } else {
            alert('Error generating history: ' + (data.error || 'Unknown error'));
        }
    });
}

// Handle asking a question
const questionForm = document.getElementById('ask-question-form');
const responseOutput = document.getElementById('response-output');

if (questionForm) {
    questionForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(questionForm);
        const response = await fetch('/ask-question/', {
            method: 'POST',
            headers: {
                'X-CSRFToken': csrfToken,
            },
            body: formData,
        });
        const data = await response.json();
        if (data.answer) {
            responseOutput.textContent = data.answer;
        } else {
            alert('Error fetching answer: ' + (data.error || 'Unknown error'));
        }
    });
}
