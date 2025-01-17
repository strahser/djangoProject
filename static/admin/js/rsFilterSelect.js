/**
 * User: Roman Suprotkin
 * Date: 2012-08-23
 * Time: 22:20
 */

//TODO: Catch non filter parameters

let jQuery = django.jQuery;
let $ = jQuery;
let emptyValue = '__empty_value__';
let djangoQSFilters = '__(exact|isnull)';
let reDjangoQSFilters = new RegExp(djangoQSFilters, '');
let reID = new RegExp(djangoQSFilters+'=[A-z0-9]*');
let queryHash = {};
let querylets = {};

let _splitUri = (function() {
    let splitRegExp = new RegExp(
        '^' +
            '(?:' +
            '([^:/?#.]+)' +                         // scheme - ignore special characters
                                                    // used by other URL parts such as :,
                                                    // ?, /, #, and .
            ':)?' +
            '(?://' +
            '(?:([^/?#]*)@)?' +                     // userInfo
            '([\\w\\d\\-\\u0100-\\uffff.%]*)' +     // domain - restrict to letters,
                                                    // digits, dashes, dots, percent
                                                    // escapes, and unicode characters.
            '(?::([0-9]+))?' +                      // port
            ')?' +
            '([^?#]+)?' +                           // path
            '(?:\\?([^#]*))?' +                     // query
            '(?:#(.*))?' +                          // fragment
            '$');

    return function (uri) {
        let split;
        split = uri.match(splitRegExp);
        return {
            'scheme':split[1],
            'user_info':split[2],
            'domain':split[3],
            'port':split[4],
            'path':split[5],
            'query_data': split[6],
            'fragment':split[7]
        }
    }; })();


function normalizeValue ( value ) {
    return value.replace(reDjangoQSFilters, '').replace('=', '')
}

jQuery.fn.filterSelect = function() {
    let form = $(document.createElement('form'))
        .attr('id', 'filterForm')
        .attr('method', 'get')
        .attr('action', '.')
        .appendTo(this.parent());

    this.appendTo(form);
    $(document.createElement('input'))
        .val(gettext("to filter"))
        .attr('type', 'button')
        .addClass('capitalize')
        .attr('id', 'submitFilters')
        .appendTo(this)
        .click(function(){
            let formValues = '';
            $('#filterForm select').each(function() {
                let value = $(this).val();
                if ( value !== emptyValue )
                    formValues += '&' + this.id + value;
            });
            location.href = form.attr('action') + '?' + formValues.slice(1);
            return false;
        });
    $(document.createElement('input'))
        .val(gettext("clear"))
        .attr('type', 'button')
        .addClass('capitalize')
        .attr('id', 'clearFilters')
        .appendTo(this)
        .click(function(){
            $('#filterForm select').each(function() {
                $(this).val(emptyValue).change();
            });

        });

    this.children('ul').each(function (){
        let $this = $(this);
        let $select = $(document.createElement('select'));
        let selectID = false;
        let emptyOption;
        let index = 0;
        $this.children('li').each(function(){
            let $a = $(this).children('a');
            let href = $a.attr('href');
            let data = href.slice(1).split('&');
            let option = $(document.createElement('option'))
                .html($a.html())
                .appendTo($select);
            for (let i = 0; i < data.length; i++ ){
                if ( queryHash.hasOwnProperty(data[i])) {
                    data.splice(i, 1);
                    i--;
                }
            }
            value = data[0];

            let value;
            if (!value) {
                value = emptyValue;
                if (index) emptyOption = option;
            } else {
                let modifier = reDjangoQSFilters.exec(value);
                let split;
                try {
                    split = value.split(modifier[0]);
                    value = modifier[0] + split[1];
                } catch (e) {
                    if (e instanceof TypeError) {
                        split = value.split('=');
                        value = '='.concat(split[1]);
                    }

                }


                if (!selectID) selectID = split[0];
            }
            option.val(value);
            if ( $(this).hasClass('selected') ) option.attr('selected', 'selected');
            index++;
        });
        if ( !!emptyOption ) emptyOption.val(querylets[selectID]);
        $select.attr('id', selectID).attr('name', selectID);
        $this.after($select);
        $this.hide();
    });

}

jQuery(document).ready(function(){
    let data = _splitUri(location.href).query_data
    if ( !!data ) {
        data = data.split('&');
        for (let i = 0; i < data.length; i++) {
            let modifier = reDjangoQSFilters.exec(data[i]);
            if ( !!modifier ) {
                let split = data[i].split(modifier[0]);
                querylets[split[0]] = modifier[0] + split[1];
            }
            queryHash[data[i]] = true;
        }
    }
    $('#change-list-filters').filterSelect();
});