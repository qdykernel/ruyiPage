"""Shared browser-side href resolution and static snapshot capture."""


RESOLVE_HREF_JS = r"""(element, value = element.getAttribute('href')) => {
    if (!value) return value;
    try {
        // A base element resolves its own href against the document's fallback
        // URL, rather than the effective baseURI it may have established.
        if (element.namespaceURI === 'http://www.w3.org/1999/xhtml'
                && element.localName === 'base') {
            return element.href;
        }
        return new URL(value, element.baseURI).href;
    } catch (_) {
        return value;
    }
}"""


ELEMENT_ATTRIBUTE_JS = """(element, name) => {
    const value = element.getAttribute(name);
    if (String(name).toLowerCase() === 'href') {
        return (%s)(element, value);
    }
    return value;
}""" % RESOLVE_HREF_JS


ELEMENT_SNAPSHOT_JS = r"""(root) => {
    const resolveHref = %s;
    // Import into a document without a browsing context so registered custom
    // element constructors do not run while taking a read-only snapshot.
    const inertDocument = root.ownerDocument.implementation.createHTMLDocument('');
    const clone = inertDocument.importNode(root, true);
    const pairs = [[root, clone]];
    for (let index = 0; index < pairs.length; index++) {
        const [original, copy] = pairs[index];
        const originalChildren = original.localName === 'template' && original.content
            ? original.content.children : original.children;
        const copyChildren = copy.localName === 'template' && copy.content
            ? copy.content.children : copy.children;
        for (let i = 0; i < originalChildren.length; i++) {
            pairs.push([originalChildren[i], copyChildren[i]]);
        }
    }

    // Mark only the clone. The source document and its attributes stay intact.
    // Choose an unused name so a site's own data attributes survive capture.
    const attributeNames = new Set();
    for (const [original] of pairs) {
        for (const attribute of original.attributes) {
            attributeNames.add(attribute.name.toLowerCase());
        }
    }
    let marker = 'data-ruyi-snapshot-href';
    while (attributeNames.has(marker)) {
        marker += '-';
    }
    const hrefs = {};
    pairs.forEach(([original, copy], index) => {
        if (index === 0 || original.hasAttribute('href')) {
            copy.setAttribute(marker, String(index));
        }
        if (original.hasAttribute('href')) {
            hrefs[String(index)] = resolveHref(original);
        }
    });
    return {html: clone.outerHTML, baseURL: root.baseURI, marker, hrefs};
}""" % RESOLVE_HREF_JS


PAGE_SNAPSHOT_JS = "() => (%s)(document.documentElement)" % ELEMENT_SNAPSHOT_JS
