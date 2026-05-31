/* ===== 客服排班系统 - 公共脚本 ===== */

const API_BASE = '/api';
const weekDayNames = ["日", "一", "二", "三", "四", "五", "六"];

async function apiGet(url) {
    const res = await fetch(API_BASE + url);
    if (!res.ok) { const e = await res.json(); throw new Error(e.error || '请求失败'); }
    return res.json();
}

async function apiPost(url, data) {
    const res = await fetch(API_BASE + url, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data) });
    if (!res.ok) { const e = await res.json(); throw new Error(e.error || '操作失败'); }
    return res.json();
}

function formatDate(date) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, '0');
    const d = String(date.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function parseDate(str) { return new Date(str + "T00:00:00"); }

function getShiftClass(shift) {
    if (!shift) return "shift-none";
    const cls = "shift-" + shift;
    return cls in {
        "shift-A班":1,"shift-B班":1,"shift-C班":1,"shift-T班":1,
        "shift-E班":1,"shift-F班":1,"shift-休息":1,"shift-放休":1,"shift-请假":1
    } ? cls : "shift-none";
}

function showToast(msg) {
    const toast = document.getElementById("toastMsg");
    toast.innerText = msg;
    toast.style.display = "block";
    setTimeout(() => { toast.style.display = "none"; }, 2500);
}

// ========== 多选下拉组件 ==========
function initMultiSelect(config) {
    const { containerId, triggerId, searchId, selectAllId, optionsId, clearId, okId, getOptions, getSelected, setSelected, placeholder } = config;
    const container = document.getElementById(containerId);
    const trigger = document.getElementById(triggerId);
    const searchInput = document.getElementById(searchId);
    const selectAllBtn = document.getElementById(selectAllId);
    const optionsContainer = document.getElementById(optionsId);

    function renderTrigger() {
        const sel = getSelected();
        const allOpts = getOptions();
        if(sel.length === 0) {
            trigger.innerHTML = `<span class="ms-placeholder">${placeholder || '请选择'}</span>`;
        } else if(sel.length === allOpts.length && allOpts.length > 0) {
            trigger.innerHTML = `<span class="ms-placeholder" style="color:#3730a3;font-weight:500;">全部 (${allOpts.length})</span>`;
        } else {
            trigger.textContent = sel.join('、');
            trigger.title = sel.join('、');
        }
    }

    function renderDropdown() {
        const sel = getSelected();
        const q = searchInput.value.toLowerCase();
        const allOpts = getOptions();
        const opts = allOpts.filter(o => o.toLowerCase().includes(q));
        if(sel.length === allOpts.length && allOpts.length > 0) {
            selectAllBtn.textContent = '取消全选';
        } else {
            selectAllBtn.textContent = '全选';
        }
        optionsContainer.innerHTML = opts.map(o => {
            const checked = sel.includes(o) ? 'checked' : '';
            return `<label class="ms-option"><input type="checkbox" value="${o}" ${checked}> ${o}</label>`;
        }).join('');
        if(opts.length === 0) {
            optionsContainer.innerHTML = `<div style="padding:16px;text-align:center;color:#94a3b8;">无匹配选项</div>`;
        }
        optionsContainer.querySelectorAll('input').forEach(cb => {
            cb.addEventListener('change', () => {
                if(cb.checked) setSelected([...getSelected(), cb.value]);
                else setSelected(getSelected().filter(v => v !== cb.value));
                renderTrigger();
                if(config.onChange) config.onChange();
            });
        });
    }

    const dropdown = container.querySelector('.ms-dropdown');

    function positionDropdown() {
        const rect = trigger.getBoundingClientRect();
        const dropdownH = dropdown.scrollHeight || 280;
        const spaceBelow = window.innerHeight - rect.bottom;
        const spaceAbove = rect.top;
        if (spaceBelow < dropdownH && spaceAbove > spaceBelow) {
            dropdown.style.top = Math.max(0, rect.top - Math.min(dropdownH, 280) - 4) + 'px';
        } else {
            dropdown.style.top = Math.min(rect.bottom + 4, window.innerHeight - Math.min(dropdownH, 280)) + 'px';
        }
        dropdown.style.left = Math.min(rect.left, window.innerWidth - 260) + 'px';
        dropdown.style.width = Math.max(rect.width, 200) + 'px';
    }

    trigger.addEventListener('click', (e) => {
        e.stopPropagation();
        const isOpen = container.classList.contains('open');
        document.querySelectorAll('.multi-select.open').forEach(ms => ms.classList.remove('open'));
        if(!isOpen) {
            container.classList.add('open');
            searchInput.value = '';
            renderDropdown();
            positionDropdown();
            setTimeout(() => searchInput.focus(), 50);
        }
    });

    searchInput.addEventListener('input', renderDropdown);
    searchInput.addEventListener('click', e => e.stopPropagation());

    selectAllBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const allOpts = getOptions();
        if(getSelected().length === allOpts.length && allOpts.length > 0) {
            setSelected([]);
        } else {
            setSelected([...allOpts]);
        }
        renderTrigger();
        renderDropdown();
        if(config.onChange) config.onChange();
    });

    document.getElementById(clearId).addEventListener('click', () => {
        setSelected([]);
        renderTrigger();
        renderDropdown();
        if(config.onChange) config.onChange();
    });

    document.getElementById(okId).addEventListener('click', () => {
        container.classList.remove('open');
    });

    document.addEventListener('click', () => {
        container.classList.remove('open');
    });

    renderTrigger();
    return { renderTrigger, renderDropdown };
}
