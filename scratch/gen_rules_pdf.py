import fitz  # PyMuPDF
import os

def create_rules_pdf():
    # Use Gautami font for Telugu support
    font_path = r"C:\Windows\Fonts\gautami.ttf"
    if not os.path.exists(font_path):
        print(f"Font not found: {font_path}")
        return

    doc = fitz.open()
    page = doc.new_page()
    
    # Title
    page.insert_text((50, 50), "జ్యోతిష్య ఫలితాల నియమములు", fontname="te", fontfile=font_path, fontsize=24, color=(0.7, 0.3, 0))
    page.insert_text((50, 80), "Ravan Astro - Results Generation Rules", fontsize=14, color=(0.3, 0.3, 0.3))
    
    context = {"y": 120, "page": page}
    
    def add_section(title, lines):
        if context["y"] > 750:
            context["page"] = doc.new_page()
            context["y"] = 50
        
        context["page"].insert_text((50, context["y"]), title, fontname="te", fontfile=font_path, fontsize=18, color=(0.1, 0.2, 0.4))
        context["y"] += 30
        
        for line in lines:
            if context["y"] > 780:
                context["page"] = doc.new_page()
                context["y"] = 50
            
            # Very basic manual wrap if line is too long (heuristic)
            if len(line) > 80:
                parts = [line[i:i+80] for i in range(0, len(line), 80)]
                for p in parts:
                    context["page"].insert_text((60, context["y"]), p, fontname="te", fontfile=font_path, fontsize=11)
                    context["y"] += 18
            else:
                context["page"].insert_text((60, context["y"]), line, fontname="te", fontfile=font_path, fontsize=11)
                context["y"] += 18
        context["y"] += 20

    # 1. Parties
    add_section("1. గ్రహ వర్గములు (Parties)", [
        "గురు వర్గము: మేషం, కర్కాటకం, సింహం, వృశ్చికం, ధనస్సు, మీనం",
        "మిత్ర గ్రహములు: సూర్య, చంద్ర, కుజ, గురు, కేతు, భూమి",
        "",
        "శని వర్గము: వృషభం, మిథునం, కన్య, తులా, మకరం, కుంభం",
        "మిత్ర గ్రహములు: శని, బుధ, శుక్ర, రాహు, మిత్ర, చిత్ర"
    ])

    # 2. Enemies
    add_section("2. బద్ధ శత్రువులు (Bitter Enemies)", [
        "కుజుడు - శుక్రుడు",
        "మిత్ర - భూమి",
        "చిత్ర - కేతు",
        "చంద్రుడు - రాహు",
        "సూర్యుడు - శని",
        "బుధుడు - గురు"
    ])

    # 3. Own Houses
    add_section("3. స్వక్షేత్రములు (Own Houses)", [
        "సూర్యుడు: సింహం | చంద్రుడు: కర్కాటకం | కుజుడు: మేషం",
        "బుధుడు: కన్య | గురు: మీనం | శుక్రుడు: తులా",
        "శని: కుంభం | రాహు: మకరం | కేతు: ధనస్సు",
        "భూమి: వృశ్చికం | మిత్ర: వృషభం | చిత్ర: మిథునం"
    ])

    # 4. House Meanings
    bhava_lines = [
        "1. ప్రథమ (తనువు): శరీరం, రూపం (శుభ: అందం, పాప: రోగం)",
        "2. ద్వితీయ (ధనము): ధనం, వాక్కు (శుభ: ధనం, పాప: ఇబ్బందులు)",
        "3. తృతీయ (సోదర): ధైర్యం (శుభ: సామాన్యం, పాప: బాధలు)",
        "4. చతుర్థ (మాతృ): ఇల్లు, భూమి (శుభ: లాభం, పాప: నష్టం)",
        "5. పంచమ (విద్యా): విద్య, సంతానం (శుభ: పాండిత్యం, పాప: సామాన్యం)",
        "6. షష్టమ (శత్రు): శత్రువు, రోగం (శుభ: జయం, పాప: అప్పులు)",
        "7. సప్తమ (కళత్ర): వివాహం (శుభ: సుఖం, పాప: సమస్యలు)",
        "8. అష్టమ (ఆయు): ఆయుష్షు (శుభ: దీర్ఘాయువు, పాప: గండం)",
        "9. నవమ (భాగ్య): భాగ్యం (శుభ: ఆస్తి, పాప: పేదరికం)",
        "10. దశమ (రాజ్య): వృత్తి (శుభ: పదవి, పాప: పోరాటం)",
        "11. ఏకాదశ (లాభ): ఆదాయం (శుభ: లాభం, పాప: ఆటంకం)",
        "12. ద్వాదశ (వ్యయ): ఖర్చు (శుభ: మోక్షం, పాప: దుబారా)"
    ]
    add_section("4. భావ ఫలితములు (House Meanings)", bhava_lines)

    # 5. Specific Rules
    add_section("5. ప్రత్యేక నిబంధనలు (Special Rules)", [
        "4వ స్థానము: సూర్యుడు మిత్రుడైతే పై అంతస్థుల భవనములు.",
        "8వ స్థానము: రాహువు శత్రువైన పాముకాటు/విషాహారం భయం.",
        "7వ స్థానము: రాహు/కేతువు ఉన్నచో రెండవ వివాహం/అక్రమ సంబంధ సూచన.",
        "10వ స్థానము: సూర్య/చంద్రులున్నచో ప్రభుత్వ ఉన్నత పదవి.",
        "లగ్నము: కుజ+శుక్ర కలయిక భార్యాభర్తల పోట్లాటలకు దారితీయును."
    ])

    # 6. Planet Rulerships
    rulership_lines = [
        "సూర్యుడు: పిత, ఆత్మ, రాజ్యము, ప్రభావము, ధైర్యము, అధికారము, నేత్రము.",
        "చంద్రుడు: బుద్ధి, నీరు, స్త్రీలు, మనస్సు, సౌందర్యము, జల సౌఖ్యము.",
        "కుజుడు: పరాక్రమము, కోపము, సేనాధిపత్యము, సోదరబలము, ఆయుధములు.",
        "బుధుడు: జ్యోతిష్యము, గణితము, వ్యాపారము, శిల్పవిద్య, వైద్యము.",
        "గురు: ధనము, వేదవిద్య, పుత్రులు, బంగారు, మంత్రిత్వము.",
        "శుక్రుడు: వివాహము, నాటకము, స్త్రీ సౌఖ్యము, వాహనము, సంగీతము.",
        "శని: ఆయుష్షు, నీచవిద్య, మరణము, దుఃఖము, ఇనుము.",
        "రాహు: కౄరత్వము, పాపము, విషములు, దొంగతనము, అపసవ్యము.",
        "కేతు: ఆత్మజ్ఞానము, సన్న్యాసత్వము, దైవభక్తి, వైరాగ్యము."
    ]
    add_section("6. గ్రహ కారకత్వములు (Rulerships)", rulership_lines)

    output_path = "astrological_rules.pdf"
    doc.save(output_path)
    doc.close()
    print(f"PDF created successfully: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    create_rules_pdf()
