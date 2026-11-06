# name_parser.py - Lógica de separación de nombres y apellidos

def parse_full_name(full_name: str) -> tuple[str, str, str]:
    """
    Separa un nombre completo en (nombre, primer_apellido, segundo_apellido)
    siguiendo la regla especificada:
    - Si tiene 4 palabras: las 2 primeras son el nombre, la 3ª el primer apellido, la 4ª el segundo apellido.
      Ej: 'Ana Maria Ramos Castillon' -> Nombre: 'Ana Maria', Apellido 1: 'Ramos', Apellido 2: 'Castillon'
    - Si tiene 3 palabras: la 1ª es el nombre, la 2ª el primer apellido, la 3ª el segundo apellido.
      Ej: 'Ana Romero Mendoza' -> Nombre: 'Ana', Apellido 1: 'Romero', Apellido 2: 'Mendoza'
    - Si tiene 2 palabras: la 1ª es el nombre, la 2ª el primer apellido, segundo apellido vacío.
    - Si tiene más de 4 palabras: las dos últimas son los apellidos y el resto el nombre compuesto.
    - Si tiene 1 palabra: es el nombre, apellidos vacíos.
    """
    words = full_name.strip().split()
    if not words:
        return "", "", ""
    
    if len(words) == 1:
        return words[0], "", ""
    elif len(words) == 2:
        return words[0], words[1], ""
    elif len(words) == 3:
        return words[0], words[1], words[2]
    elif len(words) == 4:
        return f"{words[0]} {words[1]}", words[2], words[3]
    else:
        # 5 o más palabras: las dos últimas son los apellidos y el resto el nombre
        firstname = " ".join(words[:-2])
        lastname1 = words[-2]
        lastname2 = words[-1]
        return firstname, lastname1, lastname2

if __name__ == "__main__":
    test_cases = [
        "Ana Maria Ramos Castillon",
        "Ana Romero Mendoza",
        "Juan Perez",
        "Maria del Carmen Lopez Sanchez",
        "SoloNombre"
    ]
    for tc in test_cases:
        fn, ln1, ln2 = parse_full_name(tc)
        print(f"Original: '{tc}' -> Nombre: '{fn}' | Apellido 1: '{ln1}' | Apellido 2: '{ln2}'")
