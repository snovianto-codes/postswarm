/**
 * PostSwarm Bookmarklet — Save LinkedIn post as inspiration
 *
 * To install:
 *   1. Create a new bookmark in Chrome
 *   2. Set the URL to the minified version below (everything on one line, starting with javascript:)
 *   3. Name it "📥 Save to PostSwarm"
 *   4. Click it on any LinkedIn post page to capture it
 *
 * Minified version to paste as the bookmark URL:
 *
 * javascript:(function(){var t=document.title,u=window.location.href,s=window.getSelection().toString()||'',b=document.querySelector('.feed-shared-update-v2__description,.update-components-text')?.innerText||s||'';fetch('http://localhost:8080/feed/inspiration',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:u,title:t,body:b.slice(0,1000)})}).then(function(){var d=document.createElement('div');d.style.cssText='position:fixed;top:20px;left:50%;transform:translateX(-50%);z-index:99999;padding:10px 20px;background:#0d1f17;border:1px solid #10b981;border-radius:8px;color:#10b981;font-family:sans-serif;font-size:13px;font-weight:600;box-shadow:0 4px 20px rgba(0,0,0,.5)';d.textContent='✓ Saved to PostSwarm';document.body.appendChild(d);setTimeout(function(){d.remove()},2500)}).catch(function(){alert('PostSwarm not running. Start it first at localhost:8080')})})();
 */

// ── Readable source (same logic as minified above) ──────────────────

(function () {
  var title    = document.title;
  var url      = window.location.href;
  var selected = window.getSelection().toString();

  // Try to grab the post text from LinkedIn's DOM
  var postEl = document.querySelector(
    '.feed-shared-update-v2__description, .update-components-text, .feed-shared-text'
  );
  var body = postEl ? postEl.innerText : (selected || '');
  body = body.slice(0, 1000);

  fetch('http://localhost:8080/feed/inspiration', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ url: url, title: title, body: body }),
  })
    .then(function () {
      // Show a small toast confirmation
      var toast = document.createElement('div');
      toast.style.cssText = [
        'position:fixed', 'top:20px', 'left:50%', 'transform:translateX(-50%)',
        'z-index:99999', 'padding:10px 20px',
        'background:#0d1f17', 'border:1px solid #10b981', 'border-radius:8px',
        'color:#10b981', 'font-family:sans-serif', 'font-size:13px', 'font-weight:600',
        'box-shadow:0 4px 20px rgba(0,0,0,.5)', 'pointer-events:none',
      ].join(';');
      toast.textContent = '✓ Saved to PostSwarm';
      document.body.appendChild(toast);
      setTimeout(function () { toast.remove(); }, 2500);
    })
    .catch(function () {
      alert('PostSwarm is not running.\nStart it first: bash start.sh');
    });
})();
