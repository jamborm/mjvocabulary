// Copying and distribution of this file, with or without modification,
// are permitted in any medium without royalty provided the copyright
// notice and this notice are preserved.  This file is offered as-is,
// without any warranty.

function get_caret_position(ctrl)
{
    var CaretPos = 0; // IE Support
    if (document.selection) {
        ctrl.focus();
        var Sel = document.selection.createRange();
        Sel.moveStart('character', -ctrl.value.length);
        CaretPos = Sel.text.length;
    }
    // Firefox support
    else if (ctrl.selectionStart || ctrl.selectionStart == '0')
        CaretPos = ctrl.selectionStart;
    return CaretPos;
}

function set_caret_position(ctrl, pos)
{
    if (ctrl.setSelectionRange) {
        ctrl.focus();
        ctrl.setSelectionRange(pos, pos);
    }
    else if (ctrl.createTextRange) {
        var range = ctrl.createTextRange();
        range.collapse(true);
        range.moveEnd('character', pos);
        range.moveStart('character', pos);
        range.select();
    }
}

function change_char_at(str, index, c)
{
    if(index >= str.length)
	return str;

    return str.substr(0, index) + c + str.substr(index + 1);
}

function spanish_letters(e)
{
    var keynum;
    var keychar;
    var numcheck;

    if(window.event) // IE8 and earlier
    {
        keynum = e.keyCode;
    }
    else if(e.which) // IE9/Firefox/Chrome/Opera/Safari
    {
        keynum = e.which;
    }

    keychar = String.fromCharCode(keynum);

    if (keychar == '+' || keychar == "=" || keychar == "'" || keychar == '"')
    {
	if (e.target) target = e.target;
	else if (e.srcElement) target = e.srcElement;
	if (target.nodeType == 3) // defeat Safari bug
	    target = target.parentNode;	
	v = target.value;
	i = get_caret_position (target)

	if (keychar != '"' && i > 0)
	{
	    i = i - 1;
	    c = v.charAt(i);

	    map_fr = "naeiyouNAEIYOU?!"
	    map_to = "ñáéíýóúÑÁÉÍÝÓÚ¿¡"

	    j = map_fr.indexOf(c)
	    if (j >= 0)
	    {
		target.value = change_char_at (v, i, map_to.charAt(j));
		set_caret_position (target, i + 1)
		return false;
	    }
	}
	else if (keychar == '"' && i > 0)
	{
	    i = i - 1;
	    c = v.charAt(i);
	    if (c == "u")
	    {
		target.value = change_char_at (v, i, "ü");
		set_caret_position (target, i + 1)
		return false;
	    }
	}
    }
    return true;
}
