(function() {
    'use strict';

    // Tesla Browser Fix: only enable the custom select UI in the Tesla browser.
    if (!window.isTeslaBrowser || !window.isTeslaBrowser()) {
        return;
    }

    var activeSelect = null;
    var activePortal = null;
    var lastTouchTime = 0;

    function shouldIgnoreMouse() {
        return Date.now() - lastTouchTime < 500;
    }

    function normalizeLabelText(text) {
        return text ? text.replace(/\s+/g, ' ').trim() : '';
    }

    function getLabelForSelect(select) {
        if (!select || !select.id) {
            return '';
        }
        var label = document.querySelector('label[for="' + select.id + '"]');
        if (label) {
            return normalizeLabelText(label.textContent);
        }
        return '';
    }

    function getSelectedOption(select) {
        if (!select) {
            return null;
        }
        var option = select.options[select.selectedIndex];
        return option || null;
    }

    function updateTriggerText(select, button) {
        var selected = getSelectedOption(select);
        var text = selected ? selected.textContent : '';
        if (!text) {
            text = button.getAttribute('data-placeholder') || 'Auswählen';
        }
        button.textContent = text;
    }

    function closeActive() {
        if (activePortal) {
            activePortal.style.display = 'none';
            activePortal.classList.remove('open');
        }
        if (activeSelect && activeSelect._teslaSelect) {
            activeSelect._teslaSelect.button.setAttribute('aria-expanded', 'false');
        }
        activeSelect = null;
        activePortal = null;
    }

    function isEventInsideSelect(select, target) {
        if (!select || !select._teslaSelect) {
            return false;
        }
        var button = select._teslaSelect.button;
        var portal = select._teslaSelect.portal;
        return (button && button.contains(target)) || (portal && portal.contains(target));
    }

    function handleOutsidePointer(event) {
        if (!activeSelect) {
            return;
        }
        if (!isEventInsideSelect(activeSelect, event.target)) {
            closeActive();
        }
    }

    document.addEventListener('mousedown', function(event) {
        if (shouldIgnoreMouse()) {
            return;
        }
        handleOutsidePointer(event);
    }, true);

    document.addEventListener('touchstart', function(event) {
        lastTouchTime = Date.now();
        handleOutsidePointer(event);
    }, true);

    function positionPortal(select) {
        if (!select || !select._teslaSelect) {
            return;
        }
        var portal = select._teslaSelect.portal;
        var button = select._teslaSelect.button;
        var rect = button.getBoundingClientRect();
        var viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        var viewportHeight = window.innerHeight || document.documentElement.clientHeight;

        portal.style.minWidth = rect.width + 'px';
        portal.style.left = Math.max(8, Math.min(rect.left, viewportWidth - rect.width - 8)) + 'px';
        portal.style.visibility = 'hidden';
        portal.style.display = 'block';

        var portalHeight = portal.offsetHeight;
        var top = rect.bottom;
        if (rect.bottom + portalHeight > viewportHeight && rect.top - portalHeight > 8) {
            top = rect.top - portalHeight;
        }
        portal.style.top = Math.max(8, Math.min(top, viewportHeight - portalHeight - 8)) + 'px';
        portal.style.visibility = 'visible';
    }

    function toggleSelect(select) {
        if (!select || !select._teslaSelect) {
            return;
        }
        var portal = select._teslaSelect.portal;
        if (activeSelect === select && portal.classList.contains('open')) {
            closeActive();
            return;
        }
        closeActive();
        // Tesla Browser Fix: ensure the dropdown remains open on touch.
        activeSelect = select;
        activePortal = portal;
        portal.classList.add('open');
        select._teslaSelect.button.setAttribute('aria-expanded', 'true');
        positionPortal(select);
    }

    function syncVisibility(select, wrapper) {
        if (!select || !wrapper) {
            return;
        }
        var style = window.getComputedStyle(select);
        var hidden = select.hidden || style.display === 'none' || style.visibility === 'hidden';
        wrapper.style.display = hidden ? 'none' : '';
        if (hidden && select._teslaSelect && select._teslaSelect.portal) {
            select._teslaSelect.portal.style.display = 'none';
            select._teslaSelect.portal.classList.remove('open');
        }
    }

    function buildOptionButton(select, option) {
        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'tesla-select-option';
        button.setAttribute('role', 'option');
        button.textContent = option.textContent;
        button.dataset.value = option.value;
        if (option.disabled) {
            button.disabled = true;
        }
        if (option.selected) {
            button.setAttribute('aria-selected', 'true');
        }

        button.addEventListener('touchstart', function(event) {
            lastTouchTime = Date.now();
            event.stopPropagation();
        });
        button.addEventListener('mousedown', function(event) {
            if (shouldIgnoreMouse()) {
                return;
            }
            event.stopPropagation();
        });
        button.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();
            if (option.disabled) {
                return;
            }
            select.value = option.value;
            select.dispatchEvent(new Event('change', { bubbles: true }));
            updateTriggerText(select, select._teslaSelect.button);
            closeActive();
        });
        return button;
    }

    function buildOptions(select) {
        if (!select || !select._teslaSelect) {
            return;
        }
        var portal = select._teslaSelect.portal;
        portal.innerHTML = '';
        var children = Array.prototype.slice.call(select.children);
        children.forEach(function(child) {
            if (child.tagName === 'OPTGROUP') {
                var label = document.createElement('div');
                label.className = 'tesla-select-group';
                label.textContent = child.label;
                portal.appendChild(label);
                Array.prototype.slice.call(child.children).forEach(function(option) {
                    portal.appendChild(buildOptionButton(select, option));
                });
                return;
            }
            if (child.tagName === 'OPTION') {
                portal.appendChild(buildOptionButton(select, child));
            }
        });
        updateTriggerText(select, select._teslaSelect.button);
    }

    function applyTeslaSelect(select) {
        if (!select || select._teslaSelect) {
            return;
        }

        select.classList.add('tesla-select-native');

        var wrapper = document.createElement('div');
        wrapper.className = 'tesla-select';

        var button = document.createElement('button');
        button.type = 'button';
        button.className = 'tesla-select-trigger';
        button.setAttribute('aria-haspopup', 'listbox');
        button.setAttribute('aria-expanded', 'false');

        var labelText = getLabelForSelect(select);
        if (labelText) {
            button.setAttribute('aria-label', labelText);
        }

        var portal = document.createElement('div');
        portal.className = 'tesla-select-portal';
        portal.setAttribute('role', 'listbox');
        portal.style.display = 'none';

        wrapper.appendChild(button);
        select.parentNode.insertBefore(wrapper, select.nextSibling);
        document.body.appendChild(portal);

        select._teslaSelect = {
            wrapper: wrapper,
            button: button,
            portal: portal
        };

        var toggleHandler = function(event) {
            event.preventDefault();
            event.stopPropagation();
            toggleSelect(select);
        };

        button.addEventListener('touchstart', function(event) {
            lastTouchTime = Date.now();
            toggleHandler(event);
        });

        button.addEventListener('mousedown', function(event) {
            if (shouldIgnoreMouse()) {
                return;
            }
            toggleHandler(event);
        });

        button.addEventListener('click', function(event) {
            event.preventDefault();
            event.stopPropagation();
            toggleSelect(select);
        });

        portal.addEventListener('touchstart', function(event) {
            lastTouchTime = Date.now();
            event.stopPropagation();
        });

        portal.addEventListener('mousedown', function(event) {
            if (shouldIgnoreMouse()) {
                return;
            }
            event.stopPropagation();
        });

        select.addEventListener('change', function() {
            updateTriggerText(select, button);
        });

        buildOptions(select);
        syncVisibility(select, wrapper);

        if (window.MutationObserver) {
            var observer = new MutationObserver(function(mutations) {
                var rebuild = false;
                var visibility = false;
                mutations.forEach(function(mutation) {
                    if (mutation.type === 'childList') {
                        rebuild = true;
                    }
                    if (mutation.type === 'attributes') {
                        visibility = true;
                        if (mutation.attributeName === 'disabled') {
                            button.disabled = select.disabled;
                        }
                    }
                });
                if (rebuild) {
                    buildOptions(select);
                }
                if (visibility) {
                    syncVisibility(select, wrapper);
                }
            });
            observer.observe(select, {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: ['style', 'class', 'hidden', 'disabled']
            });
        }

        button.disabled = select.disabled;
    }

    function initTeslaSelects() {
        var selects = document.querySelectorAll('select');
        for (var i = 0; i < selects.length; i++) {
            applyTeslaSelect(selects[i]);
        }
    }

    window.addEventListener('resize', function() {
        if (activeSelect) {
            positionPortal(activeSelect);
        }
    });

    window.addEventListener('scroll', function() {
        if (activeSelect) {
            positionPortal(activeSelect);
        }
    }, true);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTeslaSelects);
    } else {
        initTeslaSelects();
    }
})();
