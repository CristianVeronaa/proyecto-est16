with open(r'c:\Users\Cristian\Desktop\Proyecto_EST16\templates\editar_pagina.html', 'r', encoding='utf-8') as f:
    content = f.read()

old_text = """                                        <div class="form-check form-switch mb-2">
                                            <input class="form-check-input" type="checkbox" name="mostrar_en_inicio" value="1" {{ 'checked' if pagina and pagina.mostrar_en_inicio else '' }}>
                                            <label class="form-check-label">Mostrar en página de Inicio</label>
                                        </div>"""

# Let's use a simpler search based on the structure
search_str = '<input class="form-check-input" type="checkbox" name="mostrar_en_inicio"'
new_content = """                                        <div class="form-check form-switch mb-2">
                                            <input class="form-check-input" type="checkbox" name="mostrar_en_inicio" value="1" {{ 'checked' if pagina and pagina.mostrar_en_inicio else '' }}>
                                            <label class="form-check-label">Mostrar en página de Inicio</label>
                                        </div>
                                        <div class="form-check form-switch mb-2">
                                            <input class="form-check-input" type="checkbox" name="mostrar_en_menu" value="1" {{ 'checked' if pagina and pagina.mostrar_en_menu else '' }}>
                                            <label class="form-check-label">Aparecer en Menú Principal</label>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Prioridad en Menú (Orden)</label>
                                            <input type="number" name="orden_menu" class="form-control" value="{{ pagina.orden_menu if pagina else 0 }}" min="0">
                                            <small class="text-muted">Números bajos aparecen primero.</small>
                                        </div>"""

# Find the block containing the search string
lines = content.splitlines()
for i, line in enumerate(lines):
    if search_str in line:
        # We found line 87. We want to replace lines 86-89.
        # But let's just insert after line 89.
        # Line 89 is lines[i+2] if it has </div>
        if '</div>' in lines[i+2]:
            lines.insert(i+3, """                                        <div class="form-check form-switch mb-2">
                                            <input class="form-check-input" type="checkbox" name="mostrar_en_menu" value="1" {{ 'checked' if pagina and pagina.mostrar_en_menu else '' }}>
                                            <label class="form-check-label">Aparecer en Menú Principal</label>
                                        </div>
                                        <div class="mb-3">
                                            <label class="form-label">Prioridad en Menú (Orden)</label>
                                            <input type="number" name="orden_menu" class="form-control" value="{{ pagina.orden_menu if pagina else 0 }}" min="0">
                                            <small class="text-muted">Números bajos aparecen primero.</small>
                                        </div>""")
            break

with open(r'c:\Users\Cristian\Desktop\Proyecto_EST16\templates\editar_pagina.html', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
