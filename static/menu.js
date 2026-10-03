function createMenu(element_id) {
    const menu = document.createElement('div');
    menu.id = 'menu_for_' + element_id;
    menu.className = 'context-menu hidden';
    document.body.appendChild(menu);

    function hide() {
        menu.classList.add('hidden');
    }

    document.getElementById(element_id).addEventListener('contextmenu', event => {
        event.preventDefault();
        menu.style.left = event.pageX + 'px';
        menu.style.top = event.pageY + 'px';
        menu.classList.remove('hidden');
    });
    document.addEventListener('click', hide);
    document.addEventListener('keydown', event => { if (event.key === 'Escape') hide(); });

    function addMenuItem(text, onClickHandler) {
        const item = document.createElement('div');
        item.className = 'context-menu-item';
        item.textContent = text;
        item.onclick = onClickHandler;
        menu.appendChild(item);
    }

    return { hide, addMenuItem };
}
