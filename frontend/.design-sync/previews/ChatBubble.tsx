import { ChatBubble } from "facturemd-frontend";

export function User() {
  return <ChatBubble role="user" content="Quel code s'applique à un examen périodique?" />;
}

export function Assistant() {
  return (
    <ChatBubble
      role="assistant"
      content="Pour une visite périodique d'un patient vulnérable, les codes 15819, 15820, 15839 et 15840 s'appliquent selon l'âge et le seuil d'inscription du médecin."
    />
  );
}
