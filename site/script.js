(function () {
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
