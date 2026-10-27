import { createElement } from 'react';
import { DateInputWidget, FileInputWidget, HeaderSectionWidget, widgetRegistry } from '@openg2p/registry-widgets';
import { DOCUMENT_SLOT_VARIANT, DOCUMENTS_VARIANT, DocumentsWidget } from './DocumentsWidget';
import { EnumeratorPositionWidget } from './EnumeratorPositionWidget';
import { ETHIOPIAN_DATE_CELL, ETHIOPIAN_DATE_VARIANT, EthiopianDateInputWidget } from './EthiopianDateInputWidget';
import { FileCellWidget } from './FileCellWidget';
import { FARMER_PHOTO_VARIANT, FarmerPhotoWidget } from './FarmerPhotoWidget';
import { GeoPointWidget } from './GeoPointWidget';
import { IdentityVerificationWidget } from './IdentityVerificationWidget';
import { LocalNameWidget } from './LocalNameWidget';

// The widget package uploads a section's photo, and sets the field named by
// the widget's "image" path (record_image_document_id), only for widgets of
// type "header-section" (sectionFiles.ts). The farmer photo keeps that type in
// the section metadata so its upload takes that route, and is told apart by
// "widget-variant". Every other header-section is upstream's widget, unchanged.
type Props = { config: Record<string, unknown> } & Record<string, unknown>;

function HeaderSectionOrVariant(props: Props) {
    if (props.config['widget-variant'] === FARMER_PHOTO_VARIANT) {
        return createElement(FarmerPhotoWidget, props);
    }
    return createElement(HeaderSectionWidget, props as never);
}

widgetRegistry.register({ widget: 'header-section', component: HeaderSectionOrVariant });

// The same for documents: the package saves a section's files only from
// widgets of type "file" (sectionFiles.ts), one file per widget. A documents
// category is several "file" widgets; the first shows the category's files and
// the others render nothing. Every other file widget is upstream's.
function FileOrVariant(props: Props) {
    const variant = props.config['widget-variant'];
    if (variant === DOCUMENTS_VARIANT) return createElement(DocumentsWidget, props as never);
    if (variant === DOCUMENT_SLOT_VARIANT) return null;
    return createElement(FileInputWidget, props as never);
}

widgetRegistry.register({ widget: 'file', component: FileOrVariant });

function DateOrVariant(props: Props) {
    if (props.config['widget-variant'] === ETHIOPIAN_DATE_VARIANT) {
        return createElement(EthiopianDateInputWidget, props as never);
    }
    return createElement(DateInputWidget, props as never);
}

widgetRegistry.register({ widget: 'date', component: DateOrVariant });
// Native TableCellDate bypasses the registry for "date" columns. A custom
// column type uses TableWidget's supported WidgetRenderer/row callback path.
widgetRegistry.register({ widget: ETHIOPIAN_DATE_CELL, component: EthiopianDateInputWidget as never });

// OAN's own widget types. A widget with an object "widget-data-path" saves
// every field it names (sectionSnapshot.ts), so each of these saves its pair
// or set of fields with the section. A table cell widget gets the cell value
// and onChange from the table.
widgetRegistry.register({ widget: 'oan-file-cell', component: FileCellWidget as never });
widgetRegistry.register({ widget: 'oan-geo-point', component: GeoPointWidget as never });
widgetRegistry.register({ widget: 'oan-enumerator-position', component: EnumeratorPositionWidget as never });
widgetRegistry.register({ widget: 'oan-identity-verification', component: IdentityVerificationWidget as never });
widgetRegistry.register({ widget: 'oan-local-name', component: LocalNameWidget as never });
