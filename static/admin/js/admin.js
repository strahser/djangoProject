
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