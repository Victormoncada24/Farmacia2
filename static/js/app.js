// Evita doble envío de formularios (doble clic) y cierra alertas automáticamente.
document.addEventListener('submit', function (e) {
  var form = e.target;
  if (e.defaultPrevented) { return; }
  if (form.dataset.enviando) { e.preventDefault(); return; }
  if (form.method && form.method.toLowerCase() === 'post') {
    form.dataset.enviando = '1';
    setTimeout(function () { delete form.dataset.enviando; }, 4000);
  }
});
setTimeout(function () {
  document.querySelectorAll('.alert-success.alert-dismissible').forEach(function (a) {
    var c = bootstrap.Alert.getOrCreateInstance(a); c.close();
  });
}, 6000);
