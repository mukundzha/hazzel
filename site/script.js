(function () {
  if (window.LocomotiveScroll) {
    try {
      var loco = new LocomotiveScroll({
        el: document.querySelector("[data-scroll-container]"),
        smooth: true,
        lerp: 0.09
      });
      window.__loco = loco;
      document.querySelectorAll('a[href^="#"]').forEach(function (a) {
        a.addEventListener("click", function (e) {
          var id = a.getAttribute("href");
          if (id.length > 1) {
            var t = document.querySelector(id);
            if (t) {
              e.preventDefault();
              loco.scrollTo(t);
            }
          }
        });
      });
    } catch (e) {}
  }

  var btn = document.getElementById("copy-btn");
  var cmd = document.getElementById("install-cmd");
  if (!btn || !cmd) return;
  btn.addEventListener("click", function () {
    var text = cmd.textContent;
    function done() {
      btn.textContent = "copied";
      setTimeout(function () { btn.textContent = "copy"; }, 1500);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      var ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); } catch (e) {}
      document.body.removeChild(ta);
      done();
    }
  });
})();
