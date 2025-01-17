
jQuery(document).ready(function($) {

   // override django 1.7 timezone warning
   DateTimeShortcuts.addTimezoneWarning = function(){return false;};

});

function delete_all_class_by_name(class_name)
{
	let elements = document.querySelectorAll('.' + class_name);

	elements.forEach(function(element){

  	element.classList.remove(class_name);

  });
}
function change_display_class_by_name(class_name){
	document.querySelectorAll('.' + class_name).forEach(a=>a.style.display = "none");
}

// static/admin/js/admin.js
document.addEventListener('DOMContentLoaded', function() {
    const duplicateButtons = document.querySelectorAll('.duplicate-button');

    duplicateButtons.forEach(button => {
        button.addEventListener('click', function(event) {
            event.preventDefault();
            const paymentId = this.dataset.id;

            // Отправляем AJAX запрос на сервер для дублирования
            fetch(`/admin/duplicate-contractpayment/${paymentId}/`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCookie('csrftoken'), // Получаем CSRF токен
                },
            })
            .then(response => response.json())
            .then(data => {
                // Обновляем страницу после успешного дублирования.
                location.reload();
            })
            .catch(error => {
                console.error('Ошибка при дублировании:', error);
                alert('Ошибка при дублировании записи!');
            });
        });
    });
});


function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}