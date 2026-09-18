/*
 * Farmer intake: on-the-spot behaviour the platform's widget library lacks.
 *
 * The widget library validates one field at a time as the staff type
 * (pattern, min/max, required) but has no cross-field rules, no computed
 * fields and no calendar other than Gregorian; everything else surfaces as a
 * toast after Next. The domain services enforce these rules on every path
 * and their messages are the source of truth -- this script only tells the
 * enumerator the same thing while the cursor is still in the box:
 *
 *   1. Household: Family Size = males + females, filled in as they type and
 *      flagged inline if edited to something else; children <= family size.
 *   2. Dates: a Gregorian date fills its Ethiopic (EC) twin and vice versa,
 *      for the farmer's birth date and for any table column pair whose
 *      headers end in "(GC)" / "(EC)" (household members, crops, IDs).
 *      Both boxes are text (YYYY-MM-DD) with the same calendar button: the
 *      browser's date picker cannot show 13 months of 30 days, nor display
 *      YYYY-MM-DD outside its own locale, so one small picker is drawn
 *      here for both calendars (month / year, 7-day grid aligned by
 *      weekday, Pagumen 5 or 6).
 *   3. Photo: a non-image is refused with a message that names what is
 *      accepted, and a large image is resized to 1024px / JPEG before the
 *      widget previews it, so what is shown is what will be uploaded.
 *   4. Geo hierarchy: a level with nothing to choose from (a woreda with no
 *      kebele in Master Data) is hidden instead of an empty dropdown, and the
 *      lowest level is labelled "Village/Kebele" whichever mnemonic the
 *      Master Data pack uses.
 *   5. Other file fields (the land certificate): a hint naming the accepted
 *      types and size, and a working preview. The widget library serialises
 *      a picked File into the store as {__type:"File", name, data} and then
 *      reads it back through useBaseWidget, which turns any object with a
 *      "name" into that name -- so the widget forgets the File and its
 *      "Click to preview" opens the bare file name as a relative URL
 *      (/intake-form/farmer/new/Black.png). The File picked in this page is
 *      kept here and previewed from a blob URL instead.
 *
 * Injected by the Dockerfile as a plain <script defer> from /public; it walks
 * the DOM (data-widget-id, table headers) rather than the minified React
 * tree, and drives React-controlled inputs through the native value setter
 * plus an input event, which is how React 19 reads user edits.
 */
(function () {
  "use strict";

  var ERR_CLASS = "far-rule-error";

  /* ------------------------------------------------------------ helpers */

  function setNativeValue(input, value) {
    var proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function showError(anchor, key, message) {
    var host = anchor.closest(".table-cell-field") || anchor.closest(".widget-container") || anchor.parentElement;
    if (!host) return;
    var el = host.querySelector("." + ERR_CLASS + "[data-key=\"" + key + "\"]");
    if (!message) {
      if (el) el.remove();
      return;
    }
    if (!el) {
      el = document.createElement("p");
      el.className = ERR_CLASS + " text-xs mt-1 leading-tight";
      el.setAttribute("data-key", key);
      el.setAttribute("role", "alert");
      el.style.color = "var(--toast-failed-color, #DC3545)";
      host.appendChild(el);
    }
    el.textContent = message;
  }

  // Look the widget up inside the section the edited field belongs to, not
  // by section id from the document: the record detail view renders the
  // same section a second time as "<id>-edit" when staff click Edit
  // Details, and that copy is the one they are typing into.
  function widgetInput(section, widgetId) {
    return section.querySelector('.widget-container[data-widget-id="' + widgetId + '"] input');
  }

  function sectionKind(section) {
    return (section.getAttribute("data-section-id") || "").replace(/-edit$/, "");
  }

  function intValue(input) {
    if (!input) return null;
    var text = String(input.value || "").replace(/,/g, "").trim();
    if (text === "") return null;
    var n = Number(text);
    return Number.isFinite(n) ? n : null;
  }

  /* --------------------------------------------- 1. household family size */

  var HH = "farmer_household_information";
  var hhAutoFilled = false;

  function familySizeRule(changed, section) {
    var male = widgetInput(section, "number_of_male_members");
    var female = widgetInput(section, "number_of_female_members");
    var children = widgetInput(section, "number_of_children");
    var size = widgetInput(section, "size_of_group");
    if (!size) return;
    var m = intValue(male), f = intValue(female), c = intValue(children), s = intValue(size);

    if ((changed === male || changed === female) && m !== null && f !== null) {
      // Fill Family Size while it is blank or still holds our own earlier
      // sum; never overwrite something the enumerator typed themselves.
      if (s === null || hhAutoFilled) {
        setNativeValue(size, String(m + f));
        hhAutoFilled = true;
        s = m + f;
      }
    }
    if (changed === size) hhAutoFilled = false;

    var sizeError = "";
    if (s !== null && m !== null && f !== null && s !== m + f) {
      sizeError = "Family Size must equal Number Of Males + Number Of Females (" + m + " + " + f + " = " + (m + f) + ")";
    }
    showError(size, "family-size", sizeError);

    var childError = "";
    if (children && c !== null && s !== null && c > s) {
      childError = "Number Of Children (" + c + ") cannot exceed Family Size (" + s + ")";
    }
    if (children) showError(children, "children", childError);
  }

  /* --------------------------------------------- 2. Gregorian <-> Ethiopic */

  var JD_EPOCH = 1723856; // 1 Meskerem 1 Amete Mihret, as ethiopian_calendar.py

  function gregorianToJdn(y, m, d) {
    var a = Math.floor((14 - m) / 12), yy = y + 4800 - a, mm = m + 12 * a - 3;
    return d + Math.floor((153 * mm + 2) / 5) + 365 * yy + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400) - 32045;
  }
  function jdnToGregorian(jdn) {
    var a = jdn + 32044, b = Math.floor((4 * a + 3) / 146097), c = a - Math.floor(146097 * b / 4);
    var d = Math.floor((4 * c + 3) / 1461), e = c - Math.floor(1461 * d / 4), m = Math.floor((5 * e + 2) / 153);
    return [100 * b + d - 4800 + Math.floor(m / 10), m + 3 - 12 * Math.floor(m / 10), e - Math.floor((153 * m + 2) / 5) + 1];
  }
  function ethiopicToJdn(y, m, d) {
    return (JD_EPOCH + 365) + 365 * (y - 1) + Math.floor(y / 4) + 30 * m + d - 31;
  }
  function jdnToEthiopic(jdn) {
    var r = (((jdn - JD_EPOCH) % 1461) + 1461) % 1461;
    var n = (r % 365) + 365 * Math.floor(r / 1460);
    return [4 * Math.floor((jdn - JD_EPOCH) / 1461) + Math.floor(r / 365) - Math.floor(r / 1460), Math.floor(n / 30) + 1, (n % 30) + 1];
  }
  function ethiopicMonthLength(y, m) { return m === 13 ? (y % 4 === 3 ? 6 : 5) : 30; }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function gregorianMonthLength(y, m) {
    return m === 2 ? ((y % 4 === 0 && y % 100 !== 0) || y % 400 === 0 ? 29 : 28) : [4, 6, 9, 11].indexOf(m) >= 0 ? 30 : 31;
  }
  function gcToEc(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (y < 1 || mo < 1 || mo > 12 || d < 1 || d > gregorianMonthLength(y, mo)) return "invalid";
    var e = jdnToEthiopic(gregorianToJdn(y, mo, d));
    return e[0] + "-" + pad(e[1]) + "-" + pad(e[2]);
  }
  function ecToGc(text) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((text || "").trim());
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (y < 1 || mo < 1 || mo > 13 || d < 1 || d > ethiopicMonthLength(y, mo)) return "invalid";
    var g = jdnToGregorian(ethiopicToJdn(y, mo, d));
    return g[0] + "-" + pad(g[1]) + "-" + pad(g[2]);
  }

  var syncing = false;
  function syncPair(gc, ec, changed) {
    if (syncing || !gc || !ec) return;
    syncing = true;
    try {
      if (changed === gc) {
        // Only clear an EC value this script filled in itself, never one
        // the enumerator typed. A partial value is "still typing".
        delete gc.dataset.farAuto;
        var e = gcToEc(gc.value.trim());
        if (gc.value.trim() === "") { if (ec.value !== "" && ec.dataset.farAuto === "1") setNativeValue(ec, ""); showError(gc, "gc", ""); }
        else if (e === "invalid") showError(gc, "gc", "Not a real date (check the month and day)");
        else if (e === null) showError(gc, "gc", "");
        else { if (ec.value !== e) { setNativeValue(ec, e); ec.dataset.farAuto = "1"; } showError(gc, "gc", ""); }
        showError(ec, "ec", "");
      } else {
        delete ec.dataset.farAuto;
        var g = ecToGc(ec.value);
        if (ec.value.trim() === "") { if (gc.value !== "" && gc.dataset.farAuto === "1") setNativeValue(gc, ""); showError(ec, "ec", ""); }
        else if (g === "invalid") showError(ec, "ec", "Not a real Ethiopian date (months 1-12 have 30 days, Pagumen has 5 or 6)");
        else if (g === null) showError(ec, "ec", ""); // still typing; the widget's own pattern check speaks on blur
        else { if (gc.value !== g) { setNativeValue(gc, g); gc.dataset.farAuto = "1"; } showError(ec, "ec", ""); }
      }
    } finally {
      syncing = false;
    }
  }

  /* -------------------------------------------- 2b. calendar date picker */

  var MONTHS = {
    ec: ["Meskerem", "Tikimt", "Hidar", "Tahsas", "Tir", "Yekatit", "Megabit", "Miyazya", "Ginbot", "Sene", "Hamle", "Nehase", "Pagumen"],
    gc: ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
  };
  var WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"];
  var CAL_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>';
  var picker = null, pickerFor = null, pickerBtn = null, view = null;

  function monthLength(cal, y, m) { return cal === "ec" ? ethiopicMonthLength(y, m) : gregorianMonthLength(y, m); }
  function toJdn(cal, y, m, d) { return cal === "ec" ? ethiopicToJdn(y, m, d) : gregorianToJdn(y, m, d); }
  function todayIn(cal) {
    var d = new Date(), g = [d.getFullYear(), d.getMonth() + 1, d.getDate()];
    return cal === "ec" ? jdnToEthiopic(gregorianToJdn(g[0], g[1], g[2])) : g;
  }

  function headerOf(input) {
    var td = input.closest("td"), tr = td && td.parentElement, table = td && td.closest("table");
    if (!table) return "";
    var th = table.querySelectorAll("thead th")[Array.prototype.indexOf.call(tr.children, td)];
    return th ? (th.getAttribute("title") || th.textContent || "").trim() : "";
  }

  // Which calendar a text box holds: "_ec" widgets / "(EC)" columns are
  // Ethiopic, "_date" widgets / "(GC)" columns Gregorian, anything else none.
  function calendarOf(input) {
    if (input.type !== "text" || input.disabled || input.readOnly) return "";
    var w = input.closest(".widget-container"), id = w ? (w.getAttribute("data-widget-id") || "") : "";
    if (/_ec$/.test(id)) return "ec";
    if (/_date$/.test(id)) return "gc";
    var h = headerOf(input);
    return /\(ec\)\s*$/i.test(h) ? "ec" : /\(gc\)\s*$/i.test(h) ? "gc" : "";
  }

  function closePicker() {
    if (picker) picker.style.display = "none";
    pickerFor = null; pickerBtn = null;
  }

  function placePicker(button) {
    var r = button.getBoundingClientRect(), w = picker.offsetWidth, h = picker.offsetHeight;
    var left = Math.max(8, Math.min(r.right - w, window.innerWidth - w - 8));
    var top = r.bottom + 4;
    if (top + h > window.innerHeight - 8 && r.top - h - 4 > 8) top = r.top - h - 4;
    picker.style.left = left + "px";
    picker.style.top = top + "px";
  }

  function renderPicker() {
    var cal = view.cal, y = view.y, mo = view.m, len = monthLength(cal, y, mo), names = MONTHS[cal];
    var dow = (toJdn(cal, y, mo, 1) + 1) % 7; // JDN 0 was a Monday
    var today = todayIn(cal), sel = view.sel;
    var h = '<div class="far-ec-head">' +
      '<button type="button" class="far-ec-nav" data-nav="-1" aria-label="Previous month">&#8249;</button>' +
      '<select class="far-ec-month" aria-label="Month">' + names.map(function (n, i) { return '<option value="' + (i + 1) + '"' + (i + 1 === mo ? " selected" : "") + ">" + n + "</option>"; }).join("") + "</select>" +
      '<input class="far-ec-year" type="number" min="1" max="9999" value="' + y + '" aria-label="Year">' +
      '<button type="button" class="far-ec-nav" data-nav="1" aria-label="Next month">&#8250;</button></div>' +
      '<div class="far-ec-grid">' + WEEKDAYS.map(function (d) { return '<span class="far-ec-dow">' + d + "</span>"; }).join("");
    for (var i = 0; i < dow; i++) h += "<span></span>";
    for (var d = 1; d <= len; d++) {
      var cls = "far-ec-day" + (sel && sel[0] === y && sel[1] === mo && sel[2] === d ? " is-selected" : "") + (today[0] === y && today[1] === mo && today[2] === d ? " is-today" : "");
      h += '<button type="button" class="' + cls + '" data-day="' + d + '">' + d + "</button>";
    }
    h += '</div><div class="far-ec-foot"><button type="button" data-today="1">Today</button><span class="far-ec-cal">' + (cal === "ec" ? "Ethiopian calendar" : "Gregorian calendar") + '</span><button type="button" data-clear="1">Clear</button></div>';
    picker.innerHTML = h;
  }

  function pickerSet(value) {
    if (pickerFor) setNativeValue(pickerFor, value);
    closePicker();
  }

  function openPicker(input, button) {
    if (!picker) {
      picker = document.createElement("div");
      picker.className = "far-ec-picker";
      picker.setAttribute("role", "dialog");
      picker.setAttribute("aria-label", "Calendar");
      document.body.appendChild(picker);
      picker.addEventListener("click", function (e) {
        var t = e.target.closest("button");
        if (!t) return;
        var months = MONTHS[view.cal].length;
        if (t.dataset.day) { pickerSet(view.y + "-" + pad(view.m) + "-" + pad(+t.dataset.day)); }
        else if (t.dataset.today) { var td = todayIn(view.cal); pickerSet(td[0] + "-" + pad(td[1]) + "-" + pad(td[2])); }
        else if (t.dataset.clear) { pickerSet(""); }
        else if (t.dataset.nav) {
          view.m += +t.dataset.nav;
          if (view.m > months) { view.m = 1; view.y += 1; }
          if (view.m < 1) { view.m = months; view.y -= 1; }
          renderPicker();
        }
      });
      picker.addEventListener("change", function (e) {
        if (e.target.classList.contains("far-ec-month")) view.m = +e.target.value;
        else if (e.target.classList.contains("far-ec-year")) { var yy = parseInt(e.target.value, 10); if (yy >= 1 && yy <= 9999) view.y = yy; }
        else return;
        renderPicker();
      });
      // The widget re-validates on blur; keep focus inside the box while
      // the picker is used so the pattern message does not flash mid-pick.
      picker.addEventListener("mousedown", function (e) { if (e.target.tagName !== "INPUT" && e.target.tagName !== "SELECT") e.preventDefault(); });
    }
    var cal = calendarOf(input) || "gc";
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(input.value.trim());
    var cur = m ? [+m[1], +m[2], +m[3]] : null, start = cur || todayIn(cal);
    view = { cal: cal, y: start[0], m: start[1], sel: cur };
    pickerFor = input; pickerBtn = button;
    picker.style.display = "block";
    renderPicker();
    placePicker(button);
  }

  // The button is a sibling of the input (wrapping a React-managed input
  // in a new element breaks React's reconciliation), so it is placed over
  // the input's right end from the input's own geometry, not the parent's.
  function placeEcButton(input, btn) {
    btn.style.left = (input.offsetLeft + input.offsetWidth - 28) + "px";
    btn.style.top = (input.offsetTop + input.offsetHeight / 2) + "px";
  }

  // The table widget title-cases its headers, so "Expiry Date (GC)" comes
  // out as "Expiry Date (gc)"; the birth section, which is not a table,
  // shows the calendar tag in capitals. Make the tables match.
  function calendarTags() {
    document.querySelectorAll(".table-widget-container thead th").forEach(function (th) {
      var fix = function (t) { return t.replace(/\((gc|ec)\)/gi, function (m, c) { return "(" + c.toUpperCase() + ")"; }); };
      var title = th.getAttribute("title");
      if (title && /\((gc|ec)\)/.test(title)) th.setAttribute("title", fix(title));
      th.childNodes.forEach(function (n) { if (n.nodeType === 3 && /\((gc|ec)\)/.test(n.nodeValue)) n.nodeValue = fix(n.nodeValue); });
      th.querySelectorAll("*").forEach(function (e) { e.childNodes.forEach(function (n) { if (n.nodeType === 3 && /\((gc|ec)\)/.test(n.nodeValue)) n.nodeValue = fix(n.nodeValue); }); });
    });
  }

  function ecPickers() {
    document.querySelectorAll('.widget-container[data-widget-id$="_ec"] input[type="text"], .widget-container[data-widget-id$="_date"] input[type="text"], td input[type="text"]').forEach(function (input) {
      var btn = input.nextElementSibling;
      if (btn && btn.classList.contains("far-ec-btn")) {
        // React re-renders reset className; put the input's class back and
        // follow any width change.
        input.classList.add("far-ec-input");
        placeEcButton(input, btn);
        return;
      }
      var cal = calendarOf(input);
      if (!cal) return;
      var host = input.parentElement;
      if (getComputedStyle(host).position === "static") host.style.position = "relative";
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "far-ec-btn";
      btn.title = cal === "ec" ? "Pick an Ethiopian date" : "Pick a date";
      btn.setAttribute("aria-label", btn.title);
      btn.innerHTML = CAL_ICON;
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        if (pickerFor === input) closePicker(); else openPicker(input, btn);
      });
      input.classList.add("far-ec-input");
      input.insertAdjacentElement("afterend", btn);
      placeEcButton(input, btn);
    });
  }

  document.addEventListener("mousedown", function (e) {
    if (pickerFor && !picker.contains(e.target) && e.target !== pickerBtn && !pickerBtn.contains(e.target)) closePicker();
  }, true);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && pickerFor) closePicker(); }, true);
  window.addEventListener("resize", function () { closePicker(); ecPickers(); });
  document.addEventListener("scroll", function (e) { if (pickerFor && !(picker && picker.contains(e.target))) closePicker(); }, true);

  var BIRTH = "farmer_birth_information";
  function birthPair(changed, section) {
    syncPair(widgetInput(section, "birth_date"), widgetInput(section, "birth_date_ec"), changed);
  }

  // Table rows: cells are positional, so pair columns by their header titles.
  function tablePair(input) {
    var td = input.closest("td"), tr = td && td.parentElement, table = td && td.closest("table");
    if (!td || !table) return;
    // The table widget title-cases its headers ("Date Of Birth (gc)"), so
    // match the calendar tag case-insensitively.
    var headers = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) { return (th.getAttribute("title") || th.textContent || "").trim().toLowerCase(); });
    var idx = Array.prototype.indexOf.call(tr.children, td);
    var title = headers[idx] || "";
    var m = /^(.*)\((gc|ec)\)\s*$/.exec(title);
    if (!m) return;
    var base = m[1], other = m[2] === "gc" ? "ec" : "gc";
    var otherIdx = headers.indexOf(base + "(" + other + ")");
    if (otherIdx < 0) return;
    var otherInput = tr.children[otherIdx] && tr.children[otherIdx].querySelector("input");
    if (!otherInput) return;
    if (m[2] === "gc") syncPair(input, otherInput, input);
    else syncPair(otherInput, input, input);
  }

  /* ------------------------------------------------------------- 3. photo */

  var PHOTO_MAX_EDGE = 1024;
  var PHOTO_MAX_BYTES = 1024 * 1024;
  var PHOTO_TYPES = { "image/jpeg": 1, "image/png": 1, "image/webp": 1 };
  var PHOTO_HINT = "JPG, PNG or WebP. Larger photos are resized to 1024px automatically.";

  function photoWidget(input) {
    return input.closest('[class*="header-section-widget-"]');
  }

  function photoNote(widget, message, isError) {
    var el = widget.querySelector(".far-photo-note");
    if (!el) {
      el = document.createElement("p");
      el.className = "far-photo-note text-xs leading-tight";
      // .hdr-avatar-wrapper is styled to the avatar's fixed 120x120px, so a
      // note inside it wraps narrow and overflows the widget; put it beside
      // the avatar in the .hdr-left row, where the (hidden) metadata rows sit.
      var wrapper = widget.querySelector(".hdr-avatar-wrapper");
      var host = (wrapper && wrapper.parentElement) || widget;
      host.appendChild(el);
    }
    el.textContent = message;
    el.style.color = isError ? "var(--toast-failed-color, #DC3545)" : "var(--owt-color-text-muted, #727474)";
  }

  function replaceFiles(input, file) {
    var dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dataset.farChecked = "1";
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function shrink(file, done) {
    var url = URL.createObjectURL(file), img = new Image();
    img.onload = function () {
      var scale = Math.min(1, PHOTO_MAX_EDGE / Math.max(img.width, img.height));
      var w = Math.round(img.width * scale), h = Math.round(img.height * scale);
      var canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob(function (blob) {
        var name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
        done(blob ? new File([blob], name, { type: "image/jpeg" }) : null);
      }, "image/jpeg", 0.85);
    };
    img.onerror = function () { URL.revokeObjectURL(url); done(null); };
    img.src = url;
  }

  function photoChange(e) {
    var input = e.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
    var widget = photoWidget(input);
    if (!widget) return;
    if (input.dataset.farChecked === "1") { delete input.dataset.farChecked; return; }
    var file = input.files && input.files[0];
    if (!file) return;
    if (!PHOTO_TYPES[file.type]) {
      e.stopImmediatePropagation();
      input.value = "";
      photoNote(widget, "This file is not a photo. Choose a JPG, PNG or WebP image.", true);
      return;
    }
    // Needs resizing: stop the widget previewing the original, resize, then
    // hand it the smaller file through the same picker.
    e.stopImmediatePropagation();
    var needsShrink = file.size > PHOTO_MAX_BYTES;
    var probe = new Image(), probeUrl = URL.createObjectURL(file);
    probe.onload = function () {
      URL.revokeObjectURL(probeUrl);
      if (!needsShrink && Math.max(probe.width, probe.height) <= PHOTO_MAX_EDGE) {
        photoNote(widget, PHOTO_HINT, false);
        replaceFiles(input, file);
        return;
      }
      shrink(file, function (small) {
        if (!small) { input.value = ""; photoNote(widget, "This image could not be read. Choose another JPG, PNG or WebP photo.", true); return; }
        photoNote(widget, "Resized to " + Math.round(small.size / 1024) + " KB for upload.", false);
        replaceFiles(input, small);
      });
    };
    probe.onerror = function () { URL.revokeObjectURL(probeUrl); input.value = ""; photoNote(widget, "This image could not be read. Choose another JPG, PNG or WebP photo.", true); };
    probe.src = probeUrl;
  }

  function photoHints() {
    document.querySelectorAll('[class*="header-section-widget-"] input[type="file"]').forEach(function (input) {
      var widget = photoWidget(input);
      if (widget && !widget.querySelector(".far-photo-note")) photoNote(widget, PHOTO_HINT, false);
    });
  }

  /* ------------------------------------------------- 3b. other file cells */

  var FILE_MAX_TEXT = "up to 10 MB";
  var ACCEPT_WORDS = { "image/*": "JPG, PNG or WebP", "application/pdf": "PDF", "pdf": "PDF", "jpg": "JPG", "jpeg": "JPG", "png": "PNG", "webp": "WebP", "image/jpeg": "JPG", "image/png": "PNG", "image/webp": "WebP" };
  var pickedNames = {};
  var pickedFiles = {};

  function acceptText(input) {
    var words = [];
    (input.getAttribute("accept") || "").split(",").forEach(function (a) {
      var key = a.trim().toLowerCase().replace(/^\./, "");
      if (!key) return;
      var word = ACCEPT_WORDS[key] || key.toUpperCase();
      if (words.indexOf(word) < 0) words.push(word);
    });
    // No accept attribute: the registry's document profile applies
    // (png, jpg, jpeg, webp, pdf; 10 MB).
    return (words.length ? words.join(", ") : "PDF, JPG, PNG or WebP") + ", " + FILE_MAX_TEXT;
  }

  function fileNotes() {
    document.querySelectorAll('.widget-container[data-widget-id] input[type="file"]').forEach(function (input) {
      // The photo picker is a header-section widget INSIDE a widget-container
      // and has its own note; and once a note is placed, the input is marked
      // so a re-render of an ancestor cannot add a second one.
      if (input.dataset.farNote === "1" || input.closest('[class*="header-section-widget-"]')) return;
      var widget = input.closest(".widget-container");
      if (!widget) return;
      input.dataset.farNote = "1";
      var note = document.createElement("p");
      note.className = "far-file-note text-xs mt-1 leading-tight";
      note.style.color = "var(--owt-color-text-muted, #727474)";
      note.textContent = acceptText(input);
      // Under the button/file-name row, but never outside this widget.
      var host = input.closest(".flex-1");
      if (!host || !widget.contains(host)) host = widget;
      host.appendChild(note);
    });
  }

  // The dialog-table shows a picked file in its row as "[object Object]";
  // show the file's name instead (remembered from the picker). The File
  // itself is kept for the preview (see 5 above).
  function rememberPick(input) {
    var widget = input.closest(".widget-container");
    var id = widget && widget.getAttribute("data-widget-id");
    var file = input.files && input.files[0];
    if (!file) return;
    if (id) pickedNames[id.replace(/-dlg-\d+-/, "-")] = file.name;
    pickedFiles[file.name] = file;
  }

  function previewClick(e) {
    var button = e.target instanceof Element && e.target.closest('button[title="Click to preview"]');
    if (!button || !button.closest(".widget-container")) return;
    var name = button.textContent.trim();
    var file = pickedFiles[name];
    if (file) {
      e.preventDefault();
      e.stopImmediatePropagation();
      var url = URL.createObjectURL(file);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(function () { URL.revokeObjectURL(url); }, 60000);
    } else if (name.indexOf("/") < 0 && name.indexOf(":") < 0) {
      // A bare file name with nothing behind it (a row re-opened after a
      // reload): the widget would navigate to it as a relative URL.
      e.preventDefault();
      e.stopImmediatePropagation();
    }
  }
  function fileCellNames() {
    document.querySelectorAll(".table-widget-container td").forEach(function (td) {
      if (td.textContent.trim() !== "[object Object]") return;
      var names = Object.keys(pickedNames);
      td.textContent = names.length ? pickedNames[names[names.length - 1]] : "Attached file";
    });
  }

  /* --------------------------------------------------------- 4. geo levels */

  function geoLevels() {
    document.querySelectorAll('.widget-container[data-widget-id$="geo_hierarchy"] select').forEach(function (select) {
      var row = select.closest(".mb-\\[10px\\]") || select.parentElement.parentElement;
      if (!row) return;
      var label = row.querySelector("label span, label");
      if (label && /^(village|kebele)$/i.test(label.textContent.trim())) label.textContent = "Village/Kebele";
      // Enabled with only the placeholder means the parent is chosen, the
      // level has loaded, and Master Data holds nothing under it.
      var empty = !select.disabled && select.options.length <= 1;
      row.style.display = empty ? "none" : "";
    });
    document.querySelectorAll('.widget-container[data-widget-id$="geo_hierarchy"] label span').forEach(function (span) {
      if (/^(village|kebele)$/i.test(span.textContent.trim())) span.textContent = "Village/Kebele";
    });
  }

  /* ------------------------------------------------------------- wiring */

  // Runs after React has handled the keystroke: these rules write into other
  // controlled inputs, and doing that before React's own handler for the
  // typed field has committed re-renders the section with that field's store
  // value still stale, wiping what was just typed. Bubble phase plus a tick
  // puts the rule after React's root listener and its state flush.
  function onEdit(e) {
    var t = e.target;
    if (!(t instanceof HTMLInputElement) || t.type === "file") return;
    setTimeout(function () {
      var container = t.closest(".widget-container");
      var section = t.closest(".section");
      var sid = section ? sectionKind(section) : "";
      if (sid === HH) familySizeRule(t, section);
      else if (sid === BIRTH && container) birthPair(t, section);
      else if (t.closest("td")) tablePair(t);
    }, 0);
  }

  document.addEventListener("input", onEdit, false);
  document.addEventListener("change", onEdit, false);
  // The photo check must run BEFORE the widget sees the file, so it can stop
  // the event and hand over a resized one.
  document.addEventListener("change", function (e) {
    if (!(e.target instanceof HTMLInputElement) || e.target.type !== "file") return;
    if (photoWidget(e.target)) photoChange(e);
    else rememberPick(e.target);
  }, true);
  document.addEventListener("click", previewClick, true);

  var scheduled = false;
  function refresh() {
    scheduled = false;
    geoLevels();
    photoHints();
    fileNotes();
    fileCellNames();
    calendarTags();
    ecPickers();
  }
  new MutationObserver(function () {
    if (!scheduled) { scheduled = true; requestAnimationFrame(refresh); }
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
  refresh();
})();
